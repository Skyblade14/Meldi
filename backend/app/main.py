"""FastAPI-App. Start: `uv run uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000`."""

import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api import auth, health, messages, speech, uploads, ws
from app.config import Settings, get_settings
from app.db import init_engine, new_session
from app.migrations import upgrade_database
from app.services import ablage, message_service, seed
from app.services.notifier import Notifier
from app.stt.base import SpeechToText
from app.stt.whisper import FasterWhisperEngine

log = logging.getLogger("meldi")

GUELTIGER_HOST = re.compile(r"[A-Za-z0-9.\-]+(:\d+)?|\[[0-9A-Fa-f:]+\](:\d+)?")


def content_security_policy(host: str) -> str:
    """Nur Ressourcen vom eigenen Server – keine CDNs, kein Tracking.

    Der eigene Host steht ausdrücklich für den WebSocket da: 'self' deckt ws:/wss: nicht in jedem Browser ab
    (ältere Safari). `wss:` allein würde Verbindungen zu beliebigen Hosts erlauben.
    """
    eigener_ws = f" ws://{host} wss://{host}" if GUELTIGER_HOST.fullmatch(host) else ""
    return (
        f"default-src 'self'; connect-src 'self'{eigener_ws}; img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
    )


SECURITY_HEADERS = {
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def build_stt(settings: Settings) -> SpeechToText | None:
    if not settings.stt_enabled:
        return None
    return FasterWhisperEngine(
        settings.stt_model,
        device=settings.stt_device,
        compute_type=settings.stt_compute_type,
        cpu_threads=settings.stt_cpu_threads,
        beam_size=settings.stt_beam_size,
        download_root=settings.models_dir,
        local_files_only=settings.stt_local_files_only,
        max_audio_seconds=settings.stt_max_audio_seconds,
    )


def _load_stt(stt: SpeechToText) -> None:
    try:
        stt.load()
    except Exception:
        log.exception("Whisper-Modell konnte nicht geladen werden – Spracheingabe nicht verfügbar")


def _einsatz_vorbereiten(settings: Settings) -> None:
    with new_session() as db:
        einsatz = seed.einsatz_oeffnen(db, settings.einsatz_bezeichnung)
        log.info("Einsatz: %s (Nr. %d)", einsatz.bezeichnung, einsatz.id)
        if settings.ablage_neu_aufbauen:
            log.warning("Einsatzablage wird neu aufgebaut: %d Nachrichten", message_service.ablage_neu_aufbauen(db, einsatz))


def create_app(settings: Settings | None = None, stt: SpeechToText | None = None, *, migrate: bool = True) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if migrate:
            init_engine()
            upgrade_database()
        try:
            ablage.pruefe_schreibbar()
        except OSError:
            log.critical("Einsatzablage %s ist nicht beschreibbar, Server startet nicht", ablage.wurzel())
            raise
        ablage.aufraeumen()
        log.info("Einsatzablage: %s", ablage.wurzel())
        if settings.einsatz_bezeichnung:
            _einsatz_vorbereiten(settings)
        if app.state.stt is not None and not app.state.stt.ready:
            # Modell im Hintergrund laden, damit der Server sofort erreichbar ist.
            asyncio.get_running_loop().run_in_executor(None, _load_stt, app.state.stt)
        yield

    app = FastAPI(title="Meldi", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.stt = stt if stt is not None else build_stt(settings)
    app.state.notifier = Notifier()

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        response.headers["Content-Security-Policy"] = content_security_policy(request.headers.get("host", ""))
        if request.url.path.startswith("/api/"):
            # Sensible Einsatzdaten nicht im Browser-Cache privater Handys ablegen.
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(messages.router)
    app.include_router(speech.router)
    app.include_router(uploads.router)
    app.include_router(ws.router)

    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    else:
        log.warning("Frontend nicht gebaut (%s fehlt) – nur API verfügbar", settings.frontend_dist)

    return app
