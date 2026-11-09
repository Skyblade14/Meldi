"""Lokale Spracherkennung mit faster-whisper (CTranslate2). Läuft komplett offline auf dem ELW-Rechner."""

import asyncio
import io
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import av
import numpy as np

from app.stt.base import AudioDecodeError, AudioTooLongError, Segment, Transcript, TranscribeHint
from app.stt.postprocess import clean_text, entferne_wiederholungen, is_hallucinated_segment

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000


def decode_audio(audio: bytes) -> np.ndarray:
    """Dekodiert webm/opus (Android), mp4/aac (iOS), ogg, wav … zu 16 kHz mono float32.

    Eigene Implementierung statt faster_whisper.decode_audio, weil diese mit PyAV >= 15 nicht mehr läuft.
    PyAV bringt die FFmpeg-Bibliotheken mit – unter Windows ist keine separate Installation nötig.
    """
    try:
        with av.open(io.BytesIO(audio), mode="r") as container:
            resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
            chunks = []
            for frame in container.decode(audio=0):
                chunks += [f.to_ndarray() for f in resampler.resample(frame)]
            chunks += [f.to_ndarray() for f in resampler.resample(None)]  # Puffer leeren
    except (av.FFmpegError, IndexError, ValueError) as exc:
        raise AudioDecodeError(str(exc)) from exc
    if not chunks:
        raise AudioDecodeError("Keine Audiodaten gefunden")
    return np.concatenate(chunks, axis=1).reshape(-1).astype(np.float32) / 32768.0


class FasterWhisperEngine:
    """Hält ein Whisper-Modell im Speicher. Erkennungen laufen nacheinander in einem Worker-Thread,
    weil sich parallele Läufe auf der CPU nur gegenseitig ausbremsen."""

    def __init__(
        self,
        model: str,
        *,
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 0,
        beam_size: int = 5,
        download_root: Path | None = None,
        local_files_only: bool = False,
        max_audio_seconds: float = 90,
    ) -> None:
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._cpu_threads = cpu_threads
        self._beam_size = beam_size
        self._download_root = download_root
        self._local_files_only = local_files_only
        self._max_audio_seconds = max_audio_seconds
        self._model = None
        self._load_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")
        self._pending = 0

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def ready(self) -> bool:
        return self._model is not None

    @property
    def pending(self) -> int:
        return self._pending

    def load(self) -> None:
        from faster_whisper import WhisperModel

        with self._load_lock:
            if self._model is not None:
                return
            started = time.perf_counter()
            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
                cpu_threads=self._cpu_threads,
                download_root=str(self._download_root) if self._download_root else None,
                local_files_only=self._local_files_only,
            )
            log.info("Whisper-Modell %s geladen in %.1f s", self._model_name, time.perf_counter() - started)

    async def transcribe(self, audio: bytes, hint: TranscribeHint) -> Transcript:
        loop = asyncio.get_running_loop()
        queued = time.perf_counter()
        self._pending += 1
        try:
            return await loop.run_in_executor(self._executor, self.transcribe_sync, audio, hint, queued)
        finally:
            self._pending -= 1

    def transcribe_sync(self, audio: bytes | np.ndarray, hint: TranscribeHint, queued: float | None = None) -> Transcript:
        started = time.perf_counter()
        self.load()
        samples = decode_audio(audio) if isinstance(audio, bytes) else audio
        audio_seconds = len(samples) / SAMPLE_RATE
        if audio_seconds > self._max_audio_seconds:
            raise AudioTooLongError(f"Aufnahme zu lang ({audio_seconds:.0f} s, max. {self._max_audio_seconds:.0f} s)")

        segments_iter, _info = self._model.transcribe(
            samples,
            language="de",
            task="transcribe",
            beam_size=self._beam_size,
            initial_prompt=hint.prompt,
            hotwords=hint.hotwords,
            # Kurze Diktate: kein Kontext-Übertrag zwischen Segmenten, das reduziert Wiederholungen.
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 300},
        )
        kept: list[Segment] = []
        dropped: list[Segment] = []
        for s in segments_iter:
            seg = Segment(s.start, s.end, s.text.strip(), s.avg_logprob, s.no_speech_prob)
            (dropped if is_hallucinated_segment(seg) else kept).append(seg)

        raw_text = " ".join(s.text for s in kept + dropped if s.text)
        text = clean_text(" ".join(s.text for s in kept))
        if hint.field == "an":
            text = entferne_wiederholungen(text)
        return Transcript(
            text=text,
            raw_text=raw_text,
            model=self._model_name,
            audio_seconds=round(audio_seconds, 2),
            processing_seconds=round(time.perf_counter() - started, 3),
            queue_seconds=round(started - queued, 3) if queued else 0.0,
            segments=kept,
            dropped_segments=dropped,
        )
