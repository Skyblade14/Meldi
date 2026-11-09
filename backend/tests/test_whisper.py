"""Echte Erkennung mit Whisper. Langsam, lädt ein Modell – nur mit MELDI_TEST_WHISPER=1."""

import os
from pathlib import Path

import pytest

from app.stt.vocabulary import hint_for_field
from app.stt.whisper import FasterWhisperEngine

SYNTH = Path(__file__).resolve().parents[2] / "tools" / "stt_bench" / "audio" / "synth"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("MELDI_TEST_WHISPER") != "1", reason="MELDI_TEST_WHISPER=1 setzen"),
    pytest.mark.skipif(not SYNTH.is_dir(), reason="erst tools/stt_bench/synth.py ausführen"),
]


@pytest.fixture(scope="module")
def engine():
    e = FasterWhisperEngine(os.environ.get("MELDI_TEST_MODEL", "large-v3-turbo"),
                            download_root=Path(__file__).resolve().parents[2] / "data" / "models")
    e.load()
    return e


def test_inhalt_wird_erkannt(engine):
    r = engine.transcribe_sync((SYNTH / "thorsten_clean" / "in03.wav").read_bytes(), hint_for_field("inhalt", []))
    assert "RTW" in r.text
    assert "Rauchgasvergiftung" in r.text
    assert r.processing_seconds < 10


def test_stille_ergibt_keinen_text(engine):
    for f in (SYNTH / "leer").glob("*.wav"):
        assert engine.transcribe_sync(f.read_bytes(), hint_for_field("inhalt", [])).text == "", f.name
