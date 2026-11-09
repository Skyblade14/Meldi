import json
import logging
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from app.api.deps import DB, CurrentAnmeldung, MeldeAnmeldung
from app.config import get_settings
from app.services import ablage
from app.schemas.speech import FunktionVorschlag, SttStatus, TranscribeOut
from app.stt.base import AudioDecodeError, AudioTooLongError, SpeechToText, Transcript
from app.stt.postprocess import match_funktion
from app.stt.vocabulary import hint_for_field

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/speech", tags=["speech"])


def _stt(request: Request) -> SpeechToText | None:
    return request.app.state.stt


@router.get("/status", response_model=SttStatus)
def stt_status(request: Request, _: CurrentAnmeldung) -> SttStatus:
    stt = _stt(request)
    return SttStatus(
        aktiv=stt is not None,
        bereit=bool(stt and stt.ready),
        modell=stt.model_name if stt else None,
        warteschlange=stt.pending if stt else 0,
    )


@router.post("/transcribe", response_model=TranscribeOut)
async def transcribe(
    request: Request,
    anmeldung: MeldeAnmeldung,
    db: DB,
    audio: Annotated[UploadFile, File()],
    field: Annotated[Literal["an", "inhalt"], Form()],
    aufnahme: Annotated[str, Form(max_length=500)] = "",
) -> TranscribeOut:
    stt = _stt(request)
    if stt is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Spracherkennung ist deaktiviert")

    settings = get_settings()
    data = await audio.read(settings.stt_max_upload_bytes + 1)
    if len(data) > settings.stt_max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Aufnahme zu groß")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Leere Aufnahme")

    funktionen = anmeldung.einsatz.funktionen
    hint = hint_for_field(field, [v for f in funktionen for v in (f.name, *f.alias_liste)])
    try:
        result = await stt.transcribe(data, hint)
    except AudioDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Audioformat nicht lesbar") from None
    except AudioTooLongError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except Exception:
        log.exception("Spracherkennung fehlgeschlagen")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Spracherkennung nicht verfügbar – bitte tippen") from None

    log.info(
        "STT %s: %.1fs Audio in %.2fs (+%.2fs Warten), Modell %s",
        field, result.audio_seconds, result.processing_seconds, result.queue_seconds, result.model,
    )
    if settings.stt_keep_audio:
        _keep_audio(data, audio.content_type, field, anmeldung.funktion, aufnahme, result)

    aufnahme_id = None
    if result.text:
        # Für die Einsatzablage; landet erst beim Absenden bei der Nachricht.
        ext = _EXT.get((audio.content_type or "").split(";")[0].strip().lower(), "bin")
        aufnahme_id = ablage.vormerken(
            anmeldung.id, art="audio", feld=field, ext=ext, data=data,
            meta={"text": result.text, "rohtext": result.raw_text, "modell": result.model,
                  "audio_sekunden": round(result.audio_seconds, 1)},
        )

    vorschlaege = []
    if field == "an" and result.text:
        vorschlaege = [
            FunktionVorschlag(**m.__dict__)
            for m in match_funktion(result.text, [(f.id, f.name, f.alias_liste) for f in funktionen])
        ]
    return TranscribeOut(
        text=result.text,
        rohtext=result.raw_text,
        modell=result.model,
        audio_sekunden=result.audio_seconds,
        verarbeitung_sekunden=result.processing_seconds,
        warte_sekunden=result.queue_seconds,
        vorschlaege=vorschlaege,
        aufnahme_id=aufnahme_id,
    )


_EXT = {"audio/webm": "webm", "audio/mp4": "m4a", "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav"}


def _keep_audio(
    data: bytes, content_type: str | None, field: str, funktion: str, aufnahme: str, result: Transcript
) -> None:
    """Nur Testphase: Aufnahme + Erkennung ablegen, damit sie später als Benchmark-Material dient."""
    audio_dir = get_settings().audio_dir
    audio_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now():%Y%m%d-%H%M%S-%f}_{field}"
    ext = _EXT.get((content_type or "").split(";")[0], "bin")
    (audio_dir / f"{stem}.{ext}").write_bytes(data)
    meta = {
        "field": field, "funktion": funktion, "aufnahme": aufnahme,  # Profil + Spur-Einstellungen des Browsers
        "model": result.model, "text": result.text, "raw_text": result.raw_text,
    }
    (audio_dir / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
