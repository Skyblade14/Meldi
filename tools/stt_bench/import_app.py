"""Übernimmt in der App gesammelte Aufnahmen (MELDI_STT_KEEP_AUDIO) als echtes Benchmark-Material.

Jede Aufnahme wird anhand des live erkannten Textes dem ähnlichsten Satz aus samples.yaml zugeordnet. Nicht
eindeutig zuordenbare Aufnahmen (freie Meldungen, zu schlecht erkannt) werden übersprungen und aufgelistet.
Aufruf (aus backend/):

    uv run python ../tools/stt_bench/import_app.py johannes_drinnen [--trocken]

Ziel: audio/real/<gruppe>_<profil>/<sample-id>_<zeitstempel>.<ext>, profil = roh | verarbeitet (Browser-Audio).
"""

import argparse
import json
import shutil
from pathlib import Path

import jiwer

from common import BENCH_DIR, PROJECT_DIR, load_samples, normalize

MAX_CER = 0.5  # schlechter erkannt → Zuordnung zu unsicher
MIN_ABSTAND = 0.15  # Abstand zum zweitbesten Satz


def cer(a: str, b: str) -> float:
    a, b = normalize(a).replace(" ", ""), normalize(b).replace(" ", "")
    return min(1.0, jiwer.cer(a, b)) if a and b else 1.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("gruppe", help="Sprecher/Umgebung, z.B. johannes_drinnen")
    parser.add_argument("--quelle", type=Path, default=PROJECT_DIR / "data" / "audio")
    parser.add_argument("--trocken", action="store_true", help="nur anzeigen, nichts kopieren")
    args = parser.parse_args()

    samples = load_samples()
    uebernommen, uebersprungen = 0, []
    for meta_path in sorted(args.quelle.glob("*.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        audio = next((p for p in meta_path.parent.glob(meta_path.stem + ".*") if p.suffix != ".json"), None)
        text = meta.get("raw_text") or meta.get("text") or ""
        if audio is None or not text:
            continue
        kandidaten = sorted((cer(s["text"], text), sid) for sid, s in samples.items() if s["field"] == meta["field"])
        (best, sid), zweit = kandidaten[0], kandidaten[1][0] if len(kandidaten) > 1 else 1.0
        if best > MAX_CER or zweit - best < MIN_ABSTAND:
            uebersprungen.append(f"{audio.name}: „{text}“ (am ähnlichsten {sid}, CER {best:.0%})")
            continue
        profil = json.loads(meta.get("aufnahme") or "{}").get("profil", "verarbeitet")  # alte Aufnahmen: verarbeitet
        ziel = BENCH_DIR / "audio" / "real" / f"{args.gruppe}_{profil}" / f"{sid}_{meta_path.stem}{audio.suffix}"
        print(f"{sid:5} CER {best:4.0%}  {ziel.parent.name}/{ziel.name}  „{text}“")
        if not args.trocken:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(audio, ziel)
        uebernommen += 1

    print(f"\n{uebernommen} Aufnahmen {'zugeordnet' if args.trocken else 'übernommen'}, {len(uebersprungen)} übersprungen")
    for zeile in uebersprungen:
        print("  " + zeile)


if __name__ == "__main__":
    main()
