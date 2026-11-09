"""Erzeugt synthetische Testaufnahmen (lokale Piper-Sprachsynthese) – optional mit Einsatzlärm.

Das ersetzt keine echten Aufnahmen, gibt aber sofort eine reproduzierbare Grundlage für den
Modellvergleich. Aufruf (aus backend/):

    uv run python ../tools/stt_bench/synth.py
"""

import argparse
import wave
from pathlib import Path

import numpy as np

from common import BENCH_DIR, load_samples

STIMMEN = ["de_DE-thorsten-medium", "de_DE-kerstin-low", "de_DE-karlsson-low"]
RNG = np.random.default_rng(42)


def _brown(n: int) -> np.ndarray:
    x = np.cumsum(RNG.standard_normal(n))
    x -= np.convolve(x, np.ones(2000) / 2000, mode="same")  # Gleichanteil/Drift entfernen
    return x / (np.abs(x).max() + 1e-9)


def laerm(art: str, n: int, sr: int) -> np.ndarray:
    t = np.arange(n) / sr
    if art == "pumpe":
        # Motor/Pumpe: Grundton + Obertöne mit leichtem Schwanken, darunter Rumpeln und Rauschen.
        f0 = 47 * (1 + 0.01 * np.sin(2 * np.pi * 0.3 * t))
        phase = 2 * np.pi * np.cumsum(f0) / sr
        ton = sum(np.sin(k * phase) / k for k in range(1, 12))
        return ton / np.abs(ton).max() + 0.5 * _brown(n) + 0.15 * RNG.standard_normal(n)
    if art == "wind":
        boeen = 0.6 + 0.4 * np.sin(2 * np.pi * 0.25 * t + RNG.uniform(0, 6))
        return _brown(n) * boeen + 0.05 * RNG.standard_normal(n)
    raise ValueError(art)


def mische(sprache: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    p_s = np.mean(sprache[np.abs(sprache) > 0.01] ** 2)
    p_n = np.mean(noise**2)
    out = sprache + noise * np.sqrt(p_s / (p_n * 10 ** (snr_db / 10)))
    return out / max(1.0, np.abs(out).max())


def schreibe(path: Path, audio: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


def main() -> None:
    from piper import PiperVoice
    from piper.download_voices import download_voice

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=BENCH_DIR / "audio" / "synth")
    parser.add_argument("--stimmen", nargs="*", default=STIMMEN)
    parser.add_argument("--laerm", nargs="*", default=["pumpe:10", "pumpe:3", "wind:5"], help="art:snr_db")
    args = parser.parse_args()

    voices_dir = BENCH_DIR / "voices"
    voices_dir.mkdir(exist_ok=True)
    samples = load_samples()

    for stimme in args.stimmen:
        download_voice(stimme, voices_dir)
        voice = PiperVoice.load(voices_dir / f"{stimme}.onnx")
        sr = voice.config.sample_rate
        kurz = stimme.split("-")[1]
        for sid, sample in samples.items():
            chunks = [c.audio_float_array for c in voice.synthesize(sample["text"])]
            pause = np.zeros(int(0.6 * sr), dtype=np.float32)
            sprache = np.concatenate([pause, *chunks, pause]) * 0.8
            schreibe(args.out / f"{kurz}_clean" / f"{sid}.wav", sprache, sr)
            for spec in args.laerm:
                art, snr = spec.split(":")
                noisy = mische(sprache, laerm(art, len(sprache), sr), float(snr))
                schreibe(args.out / f"{kurz}_{art}{snr}db" / f"{sid}.wav", noisy, sr)
        print(f"{stimme}: {len(samples)} Sätze × {1 + len(args.laerm)} Varianten")

    # Aufnahmen ohne Sprache: hier darf nichts erkannt werden (Halluzinations-Test).
    sr = 16_000
    for i, art in enumerate(["stille", "pumpe", "wind", "pumpe", "wind"]):
        n = int(RNG.uniform(3, 8) * sr)
        audio = 0.002 * RNG.standard_normal(n) if art == "stille" else 0.3 * laerm(art, n, sr)
        schreibe(args.out / "leer" / f"leer{i + 1:02d}_{art}.wav", audio, sr)
    print(f"Fertig → {args.out}")


if __name__ == "__main__":
    main()
