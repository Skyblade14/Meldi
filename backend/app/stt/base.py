"""Schnittstelle der Spracherkennung. Implementierungen sind austauschbar (Whisper, Fake für Tests, …)."""

from dataclasses import dataclass, field
from typing import Protocol


class AudioDecodeError(Exception):
    """Die hochgeladene Datei konnte nicht als Audio gelesen werden."""


class AudioTooLongError(Exception):
    pass


@dataclass(frozen=True)
class TranscribeHint:
    """Kontext für die Erkennung eines bestimmten Formularfelds."""

    field: str
    prompt: str | None = None
    hotwords: str | None = None


@dataclass
class Segment:
    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float


@dataclass
class Transcript:
    text: str
    raw_text: str  # vor der Nachbearbeitung
    model: str
    audio_seconds: float
    processing_seconds: float  # reine Rechenzeit
    queue_seconds: float = 0.0  # Wartezeit, falls andere Erkennungen vorher dran waren
    segments: list[Segment] = field(default_factory=list)
    dropped_segments: list[Segment] = field(default_factory=list)


class SpeechToText(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def ready(self) -> bool: ...

    @property
    def pending(self) -> int: ...

    def load(self) -> None: ...

    async def transcribe(self, audio: bytes, hint: TranscribeHint) -> Transcript: ...
