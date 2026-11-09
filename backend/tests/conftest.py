import asyncio
import importlib.util
import os
import threading

os.environ["MELDI_COOKIE_SECURE"] = "false"  # TestClient spricht http://
os.environ["MELDI_STT_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import init_engine, new_session
from app.main import create_app
from app.migrations import upgrade_database
from app.services.seed import neuer_einsatz
from app.stt.base import Transcript, TranscribeHint


# Ohne die Gruppe `ui` (normales `uv sync`) laufen die übrigen Tests trotzdem.
collect_ignore = [] if importlib.util.find_spec("playwright") else ["ui"]


class FakeSTT:
    """Liefert vorgegebenen Text statt echter Erkennung.

    `antworten` wird der Reihe nach abgearbeitet (Text oder Exception), danach gilt `next_text`. Mit `anhalten()`
    bleibt die Erkennung hängen, bis `freigeben()` kommt. So lässt sich der Zustand „Erkenne …“ prüfen.
    """

    model_name = "fake"
    ready = True
    pending = 0

    def __init__(self) -> None:
        self.next_text = "Einsatzabschnitt Brand"
        self.antworten: list[str | Exception] = []
        self.calls: list[tuple[bytes, TranscribeHint]] = []
        self._frei = threading.Event()
        self._frei.set()

    def load(self) -> None:
        pass

    def anhalten(self) -> None:
        self._frei.clear()

    def freigeben(self) -> None:
        self._frei.set()

    async def transcribe(self, audio: bytes, hint: TranscribeHint) -> Transcript:
        self.calls.append((audio, hint))
        while not self._frei.is_set():
            await asyncio.sleep(0.01)  # nicht blockieren: Der Event-Loop bedient auch die übrigen Anfragen
        antwort = self.antworten.pop(0) if self.antworten else self.next_text
        if isinstance(antwort, Exception):
            raise antwort
        return Transcript(text=antwort, raw_text=antwort, model="fake", audio_seconds=2.0, processing_seconds=0.1)


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    monkeypatch.setenv("MELDI_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    init_engine()
    upgrade_database()
    with new_session() as db:
        neuer_einsatz(db, "Test-Einsatz")
    yield
    get_settings.cache_clear()


@pytest.fixture
def stt():
    return FakeSTT()


@pytest.fixture
def app(db_url, stt):
    return create_app(stt=stt, migrate=False)


def _client(app, name: str, rolle: str, funktion: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"name": name, "rolle": rolle, "funktion": funktion})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def melder(app):
    with _client(app, "Melder 1", "melder", "EA Brand") as c:
        yield c


@pytest.fixture
def melder2(app):
    with _client(app, "Melder 2", "melder", "EA Wasserversorgung") as c:
        yield c


@pytest.fixture
def elw(app):
    with _client(app, "ELW", "elw", "ELW") as c:
        yield c


@pytest.fixture
def beobachter(app):
    with _client(app, "Beobachter", "beobachter", "Einsatzleiter") as c:
        yield c
