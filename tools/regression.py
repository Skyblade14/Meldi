#!/usr/bin/env python3
"""Regressionstests in einem Befehl, unter Linux und Windows (nur Standardbibliothek).

    python tools/regression.py schnell   pytest, Vitest, vue-tsc
    python tools/regression.py voll      zusätzlich Frontend-Build und UI-Tests
    python tools/regression.py whisper   zusätzlich echtes Whisper-Modell

UI-Tests einmalig einrichten: cd backend && uv sync --all-groups && uv run --group ui playwright install chromium webkit
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

UI_ARGUMENTE = [
    "-m", "ui", "--timeout=120", "--tracing=retain-on-failure", "--screenshot=only-on-failure",
    "--output=test-results",
]

SCHNELL = [
    ("Backend (pytest)", BACKEND, ["uv", "run", "pytest", "-q"], {}),
    ("Frontend (Vitest)", FRONTEND, ["npm", "test"], {}),
    ("Typen (vue-tsc)", FRONTEND, ["npm", "run", "typecheck"], {}),
]
# Der Build kommt zuerst: Ohne frontend/dist überspringt test_regeln die Prüfung auf externe URLs.
BUILD = [("Frontend-Build", FRONTEND, ["npm", "run", "build"], {})]
UI = [("UI-Tests (Playwright)", BACKEND, ["uv", "run", "--group", "ui", "pytest", "-q", *UI_ARGUMENTE], {})]
WHISPER = [
    ("Spracherkennung (Whisper)", BACKEND, ["uv", "run", "pytest", "-q", "-m", "slow"], {"MELDI_TEST_WHISPER": "1"}),
]
STUFEN = {"schnell": SCHNELL, "voll": BUILD + SCHNELL + UI, "whisper": BUILD + SCHNELL + UI + WHISPER}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stufe", choices=STUFEN, nargs="?", default="schnell")
    stufe = parser.parse_args().stufe

    ergebnisse: list[tuple[str, bool, float]] = []
    for name, ordner, befehl, umgebung in STUFEN[stufe]:
        programm = shutil.which(befehl[0])  # unter Windows ist npm eine .cmd-Datei
        if programm is None:
            print(f"{befehl[0]} nicht gefunden", file=sys.stderr)
            return 2
        print(f"\n=== {name} ===", flush=True)
        start = time.monotonic()
        ok = subprocess.run([programm, *befehl[1:]], cwd=ordner, env={**os.environ, **umgebung}).returncode == 0
        ergebnisse.append((name, ok, time.monotonic() - start))
        if not ok:
            break  # die folgenden Stufen bauen darauf auf

    print("\n=== Ergebnis ===")
    for name, ok, sekunden in ergebnisse:
        print(f"{'OK    ' if ok else 'FEHLER'} {name} ({sekunden:.0f} s)")
    gesamt = sum(s for *_, s in ergebnisse)
    bestanden = all(ok for _, ok, _ in ergebnisse) and len(ergebnisse) == len(STUFEN[stufe])
    print(f"{'Bestanden' if bestanden else 'NICHT bestanden'} in {gesamt:.0f} s")
    return 0 if bestanden else 1


if __name__ == "__main__":
    sys.exit(main())
