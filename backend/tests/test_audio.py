"""Dekodierung der Formate, die Handy-Browser per MediaRecorder liefern."""

import io
import wave

import av
import numpy as np
import pytest

from app.stt.base import AudioDecodeError
from app.stt.whisper import SAMPLE_RATE, decode_audio


def sinus(seconds: float, rate: int) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def encode(fmt: str, codec: str, rate: int = 48_000, seconds: float = 1.5) -> bytes:
    buf = io.BytesIO()
    with av.open(buf, mode="w", format=fmt) as out:
        stream = out.add_stream(codec, rate=rate, layout="mono")
        samples = sinus(seconds, rate).reshape(1, -1)
        frame_size = stream.codec_context.frame_size or 1024
        for i in range(0, samples.shape[1], frame_size):
            frame = av.AudioFrame.from_ndarray(samples[:, i : i + frame_size], format="flt", layout="mono")
            frame.rate = rate
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    return buf.getvalue()


@pytest.mark.parametrize(("fmt", "codec"), [("webm", "libopus"), ("mp4", "aac"), ("ogg", "libopus")])
def test_browserformate(fmt, codec):
    samples = decode_audio(encode(fmt, codec))
    assert samples.dtype == np.float32
    assert abs(len(samples) / SAMPLE_RATE - 1.5) < 0.15


def test_wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22_050)
        wf.writeframes((sinus(2.0, 22_050) * 32767).astype(np.int16).tobytes())
    assert abs(len(decode_audio(buf.getvalue())) / SAMPLE_RATE - 2.0) < 0.01


def test_kaputte_datei():
    with pytest.raises(AudioDecodeError):
        decode_audio(b"das ist kein audio" * 100)
