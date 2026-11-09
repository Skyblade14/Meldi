#!/usr/bin/env python3
"""Hält sensible Dateien und Adressen aus dem öffentlichen Repository fern (nur Standardbibliothek).

    python tools/leak_check.py [DATEI ...]   ohne Angabe: alle versionierten Dateien

Läuft als pre-commit-Hook und in GitHub Actions und ergänzt gitleaks, das nur Schlüssel und Passwörter erkennt.
Konkrete Begriffe wie Namen oder Adressen gehören in `.leak-begriffe.local` (ein Begriff pro Zeile, gitignored),
weil eine Liste im Repository selbst das Leck wäre. Treffer werden nur mit Datei und Zeile gemeldet, denn die Logs
von GitHub Actions sind bei einem öffentlichen Repository öffentlich.
"""

import ipaddress
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BEGRIFFE_DATEI = ROOT / ".leak-begriffe.local"

MAX_BYTES = 1024 * 1024
SCHLUESSEL_ENDUNGEN = {".pem", ".key", ".crt", ".csr", ".p12", ".pfx"}
# Lookarounds, damit vierstellige Teile längerer Versionsnummern nicht als Adresse gelten.
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


def adresse_verraet_etwas(text: str) -> bool:
    """Private Adressen sind überall gleich und daher harmlos. Tailscale-Adressen zählen nicht als privat."""
    try:
        return not ipaddress.ip_address(text).is_private
    except ValueError:
        return False


def verbotener_name(pfad: Path) -> bool:
    name = pfad.name.lower()
    umgebung = (name == ".env" or name.startswith(".env.")) and name != ".env.example"
    return umgebung or pfad.suffix.lower() in SCHLUESSEL_ENDUNGEN


def pruefe_datei(pfad: Path, begriffe: list[str]) -> list[str]:
    if verbotener_name(pfad):
        return [f"{pfad}: Schlüssel, Zertifikat oder Umgebungsdatei"]
    if pfad.stat().st_size > MAX_BYTES:
        return [f"{pfad}: größer als {MAX_BYTES // 1024} KiB"]
    daten = pfad.read_bytes()
    # Prüft den Inhalt statt der Endung, damit auch eine umbenannte Aufnahme oder Datenbank auffällt.
    if b"\0" in daten:
        return [f"{pfad}: Binärdatei (Aufnahme, Foto, Datenbank?)"]

    befunde = []
    for nr, zeile in enumerate(daten.decode("utf-8", "replace").splitlines(), start=1):
        if any(adresse_verraet_etwas(treffer) for treffer in IPV4.findall(zeile)):
            befunde.append(f"{pfad}:{nr}: öffentliche oder Tailscale-Adresse")
        klein = zeile.casefold()
        if any(begriff in klein for begriff in begriffe):
            befunde.append(f"{pfad}:{nr}: Begriff aus {BEGRIFFE_DATEI.name}")
    return befunde


def lade_begriffe() -> list[str]:
    if not BEGRIFFE_DATEI.is_file():
        return []
    zeilen = (z.strip().casefold() for z in BEGRIFFE_DATEI.read_text(encoding="utf-8").splitlines())
    return [z for z in zeilen if z and not z.startswith("#")]


def versionierte_dateien() -> list[Path]:
    ausgabe = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True).stdout
    return [ROOT / name for name in ausgabe.decode("utf-8").split("\0") if name]


def main(argumente: list[str]) -> int:
    dateien = [Path(a) for a in argumente] or versionierte_dateien()
    begriffe = lade_begriffe()
    # Versionierte, aber gerade gelöschte Dateien gibt es nicht mehr auf der Platte.
    befunde = [b for d in dateien if d.is_file() for b in pruefe_datei(d, begriffe)]
    for befund in befunde:
        print(befund, file=sys.stderr)
    return 1 if befunde else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
