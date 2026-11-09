"""Misst die Spracherkennung auf den Testaufnahmen: Fehlerrate, Fachbegriffe, Empfänger-Zuordnung, Tempo.

Nutzt exakt denselben Erkennungsweg wie die App (Prompts, VAD, Nachbearbeitung). Aufruf (aus backend/):

    uv run python ../tools/stt_bench/run.py
    uv run python ../tools/stt_bench/run.py --audio ../tools/stt_bench/audio/real

Ordnerstruktur:  <audio>/<gruppe>/<sample-id>[_beliebig].<wav|m4a|webm|ogg|mp3>
Gruppe „leer“:   Aufnahmen ohne Sprache – hier darf nichts erkannt werden.
"""

import argparse
import csv
import os
import statistics
import time
from collections import defaultdict
from pathlib import Path

import jiwer

from common import BENCH_DIR, load_samples, normalize

from app.services.seed import STANDARD_FUNKTIONEN  # noqa: E402
from app.stt.postprocess import match_funktion  # noqa: E402
from app.stt.vocabulary import hint_for_field  # noqa: E402
from app.stt.base import TranscribeHint  # noqa: E402
from app.stt.whisper import FasterWhisperEngine, decode_audio  # noqa: E402

AUDIO_EXT = {".wav", ".m4a", ".mp4", ".webm", ".ogg", ".mp3", ".opus"}
FUNKTIONEN = [(i, name, [a.strip() for a in aliase.split(",") if a.strip()])
              for i, (name, aliase) in enumerate(STANDARD_FUNKTIONEN)]
FUNKTION_NAMEN = [v for _, name, aliases in FUNKTIONEN for v in (name, *aliases)]


def finde_aufnahmen(root: Path, samples: dict) -> list[tuple[str, str, Path]]:
    """→ [(gruppe, sample_id, pfad)]"""
    found = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in AUDIO_EXT:
            continue
        gruppe = str(path.parent.relative_to(root))
        sid = path.stem.split("_")[0]
        if "leer" in Path(gruppe).parts or sid in samples:
            found.append((gruppe, sid, path))
    return found


def bewerte(sample: dict | None, text: str) -> dict:
    if sample is None:  # Leer-Aufnahme
        return {"wer": None, "halluziniert": bool(text.strip())}
    ref, hyp = normalize(sample["text"]), normalize(text)
    row = {
        "wer": jiwer.wer(ref, hyp) if hyp else 1.0,
        # Zeichenfehlerrate ohne Leerzeichen: „Angriff Trupp“ statt „Angriffstrupp“ zählt kaum.
        "cer": min(1.0, jiwer.cer(ref.replace(" ", ""), hyp.replace(" ", ""))) if hyp else 1.0,
    }
    if terms := sample.get("terms"):
        row["begriffe"] = sum(normalize(t) in hyp for t in terms) / len(terms)
    if sample["field"] == "an":
        matches = match_funktion(text, FUNKTIONEN)
        row["an_treffer"] = bool(matches) and matches[0].name == sample["expect"]
        row["an_score"] = matches[0].score if matches else 0
        row["an_erkannt"] = matches[0].name if matches else ""
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["large-v3-turbo"])
    parser.add_argument("--audio", type=Path, default=BENCH_DIR / "audio")
    parser.add_argument("--gruppen", nargs="*", help="nur diese Gruppen (Teilstring-Match)")
    parser.add_argument("--feld", choices=["an", "inhalt"], help="nur Aufnahmen für dieses Feld")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--beam", type=int, default=5)
    parser.add_argument("--ohne-prompt", action="store_true", help="ohne Feuerwehr-Vokabular (Vergleich)")
    parser.add_argument("--out", type=Path, default=BENCH_DIR / "results")
    args = parser.parse_args()

    samples = load_samples()
    aufnahmen = finde_aufnahmen(args.audio, samples)
    if args.gruppen:
        aufnahmen = [a for a in aufnahmen if any(g in a[0] for g in args.gruppen)]
    if args.feld:
        aufnahmen = [a for a in aufnahmen if a[1] in samples and samples[a[1]]["field"] == args.feld]
    if not aufnahmen:
        raise SystemExit(f"Keine Aufnahmen unter {args.audio} gefunden (erst synth.py ausführen?)")
    print(f"{len(aufnahmen)} Aufnahmen, Modelle: {', '.join(args.models)}, Gerät: {args.device}, "
          f"CPU-Kerne: {os.cpu_count()}, Prompt: {'nein' if args.ohne_prompt else 'ja'}\n")

    # Audio einmal vorab dekodieren, damit nur die Erkennung gemessen wird.
    audio = {p: decode_audio(p.read_bytes()) for _, _, p in aufnahmen}

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    rows = []
    for model in args.models:
        engine = FasterWhisperEngine(model, device=args.device, compute_type=args.compute_type,
                                     cpu_threads=args.threads, beam_size=args.beam,
                                     download_root=BENCH_DIR.parent.parent / "data" / "models")
        t0 = time.perf_counter()
        engine.load()
        print(f"[{model}] geladen in {time.perf_counter() - t0:.1f} s")
        # Aufwärmen (erste Inferenz ist langsamer)
        engine.transcribe_sync(audio[aufnahmen[0][2]], TranscribeHint(field="inhalt"))
        for i, (gruppe, sid, path) in enumerate(aufnahmen, 1):
            sample = samples.get(sid)
            field = sample["field"] if sample else "inhalt"
            hint = TranscribeHint(field=field) if args.ohne_prompt else hint_for_field(field, FUNKTION_NAMEN)
            res = engine.transcribe_sync(audio[path], hint)
            row = {"modell": model, "gruppe": gruppe, "id": sid, "feld": field, "text": res.text,
                   "audio_s": res.audio_seconds, "rechen_s": res.processing_seconds, **bewerte(sample, res.text)}
            rows.append(row)
            if i % 25 == 0:
                print(f"  {i}/{len(aufnahmen)}")
        del engine

    with open(args.out / f"{stamp}_details.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        writer.writeheader()
        writer.writerows(rows)

    report = zusammenfassung(rows, args)
    (args.out / f"{stamp}_summary.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Details: {args.out / f'{stamp}_details.csv'}")


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def _fmt(v, pct=False) -> str:
    if v is None:
        return "–"
    return f"{v * 100:.0f} %" if pct else f"{v:.2f}"


def zusammenfassung(rows: list[dict], args) -> str:
    out = [f"# STT-Benchmark ({time.strftime('%d.%m.%Y %H:%M')})", "",
           f"Gerät: {args.device}, compute: {args.compute_type}, beam: {args.beam}, "
           f"Prompt: {'nein' if args.ohne_prompt else 'ja'}, CPU-Kerne: {os.cpu_count()}", ""]

    out += ["## Gesamt je Modell", "",
            "| Modell | WER Inhalt | CER Inhalt | Fachbegriffe | Empfänger richtig | Halluzination (leer) | Ø Rechenzeit | Echtzeitfaktor |",
            "|---|---|---|---|---|---|---|---|"]
    by_model = defaultdict(list)
    for r in rows:
        by_model[r["modell"]].append(r)
    for model, rs in by_model.items():
        inhalt = [r for r in rs if r["feld"] == "inhalt" and r["wer"] is not None]
        an = [r for r in rs if "an_treffer" in r]
        leer = [r for r in rs if "halluziniert" in r]
        sprache = [r for r in rs if r["wer"] is not None]
        out.append("| {} | {} | {} | {} | {} | {} | {} s | {} |".format(
            model,
            _fmt(_mean(r["wer"] for r in inhalt), True),
            _fmt(_mean(r["cer"] for r in inhalt), True),
            _fmt(_mean(r.get("begriffe") for r in inhalt), True),
            _fmt(_mean(r["an_treffer"] for r in an), True),
            f"{sum(r['halluziniert'] for r in leer)}/{len(leer)}" if leer else "–",
            _fmt(_mean(r["rechen_s"] for r in sprache)),
            _fmt(_mean(r["rechen_s"] / r["audio_s"] for r in sprache if r["audio_s"])),
        ))

    out += ["", "## WER Inhalt je Aufnahmebedingung", ""]
    gruppen = sorted({r["gruppe"] for r in rows if r["wer"] is not None})
    out += ["| Modell | " + " | ".join(gruppen) + " |", "|---" * (len(gruppen) + 1) + "|"]
    for model, rs in by_model.items():
        cells = [_fmt(_mean(r["wer"] for r in rs if r["gruppe"] == g and r["feld"] == "inhalt"), True) for g in gruppen]
        out.append(f"| {model} | " + " | ".join(cells) + " |")

    out += ["", "_WER = Wortfehlerrate, CER = Zeichenfehlerrate ohne Leerzeichen (0 % = perfekt). "
            "Echtzeitfaktor < 1 = schneller als die Aufnahme lang ist._", ""]
    return "\n".join(out)


if __name__ == "__main__":
    main()
