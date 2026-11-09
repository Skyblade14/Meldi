"""Gemeinsame Hilfsfunktionen für synth.py und run.py."""

import re
import sys
from pathlib import Path

import yaml

BENCH_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BENCH_DIR.parent.parent
sys.path.insert(0, str(PROJECT_DIR / "backend"))

ZAHLWOERTER = {
    "zwei": "2", "drei": "3", "vier": "4", "fünf": "5", "sechs": "6", "sieben": "7", "acht": "8",
    "neun": "9", "zehn": "10", "zwanzig": "20", "dreißig": "30", "vierzig": "40", "fünfzig": "50",
    "hundert": "100", "zweihundert": "200", "dreihundert": "300",
}


def load_samples() -> dict[str, dict]:
    with open(BENCH_DIR / "samples.yaml", encoding="utf-8") as f:
        return {s["id"]: s for s in yaml.safe_load(f)}


def normalize(text: str) -> str:
    """Vergleichsform: klein, ohne Satzzeichen, Zahlwörter als Ziffern."""
    text = text.lower().replace("-", " ")
    text = re.sub(r"[^\wäöüß ]", " ", text)
    words = [ZAHLWOERTER.get(w, w) for w in text.split()]
    return " ".join(words)
