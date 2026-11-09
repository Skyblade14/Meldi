#!/usr/bin/env python3
"""Windows-Installationspaket bauen und Releases vorbereiten (nur Standardbibliothek).

    python tools/paket.py setze-version 0.2.0-rc.1      Version in allen Manifesten setzen, Changelog abschließen
    python tools/paket.py pruefe-tag v0.2.0-rc.1        Tag, Manifeste und Changelog passen zusammen
    python tools/paket.py notizen v0.2.0-rc.1 DATEI     Release-Notizen aus CHANGELOG.md schreiben
    python tools/paket.py bauen [--ausgabe paket]       ZIP bauen, braucht ein aktuelles frontend/dist
    python tools/paket.py rauchtest ZIP                 Installieren, Update und Rückweg echt durchspielen (nur Windows)

Das Paket enthält App, fertiges Frontend, uv und Caddy. Python und die Bibliotheken lädt der Installer auf dem
ELW-Rechner, geprüft gegen die Hashes aus uv.lock.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Wie bei Dependabot nur Versionen, die mindestens 7 Tage alt sind. Dependabot pflegt diese Einträge nicht.
PYTHON_VERSION = "3.12.15"  # die Windows-Rechner sollen exakt das bekommen, was der Rauchtest geprüft hat


@dataclass(frozen=True)
class Download:
    url: str
    sha256: str
    # Datei im ZIP-Archiv → Pfad im Paket. Leerer Schlüssel: Der Download ist selbst die Datei.
    inhalt: dict[str, str] = field(default_factory=dict)


WERKZEUGE = [
    Download(
        "https://github.com/caddyserver/caddy/releases/download/v2.11.7/caddy_2.11.7_windows_amd64.zip",
        "0a1edc0b799512051c57071ce0e798d3f2cf67dc98171366f1d2b326072e3b06",
        {"caddy.exe": "deploy/bin/caddy.exe", "LICENSE": "lizenzen/caddy-LICENSE.txt"},
    ),
    Download(
        "https://github.com/astral-sh/uv/releases/download/0.13.6/uv-x86_64-pc-windows-msvc.zip",
        "a2a8820d5eea32f08ef467ef3b7f66883a9b076d5737a2fc2fbb5f458d1bb50f",
        {"uv.exe": "deploy/bin/uv.exe"},
    ),
    Download(
        "https://raw.githubusercontent.com/astral-sh/uv/0.13.6/LICENSE-MIT",
        "860e3d7a86b84e6a7012c7a635fc64df475cebc6cce34dfeb73a5982ec58176c",
        {"": "lizenzen/uv-LICENSE-MIT.txt"},
    ),
    Download(
        "https://raw.githubusercontent.com/astral-sh/uv/0.13.6/LICENSE-APACHE",
        "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
        {"": "lizenzen/uv-LICENSE-APACHE.txt"},
    ),
]

# Positivliste: Was hier nicht steht, kann nicht ins öffentliche Paket geraten.
VERSIONIERT = (
    "LICENSE", "backend/alembic.ini", "backend/alembic/", "backend/app/", "backend/pyproject.toml", "backend/uv.lock",
    "deploy/Caddyfile", "deploy/installieren.ps1",
)
PFLICHT = (
    "VERSION", "LICENSE", "installieren.cmd", "backend/alembic.ini", "backend/app/main.py", "backend/uv.lock",
    "deploy/Caddyfile", "deploy/installieren.ps1", "deploy/bin/caddy.exe", "deploy/bin/uv.exe", "frontend/dist/index.html",
)
VERBOTENE_ENDUNGEN = {
    ".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".pem", ".key", ".crt", ".csr", ".p12", ".pfx", ".pyc",
    ".wav", ".webm", ".ogg", ".opus", ".mp3", ".m4a", ".mp4", ".flac", ".jpg", ".jpeg", ".heic",
}
VERBOTENE_ORDNER = {"data", "tests", "node_modules", ".venv", "__pycache__", ".git", "test-results"}

VERSION_MUSTER = re.compile(r"\d+\.\d+\.\d+(-rc\.\d+)?")
UNVEROEFFENTLICHT = "## Unveröffentlicht"

# Entfernen, sobald die Bedingungen für den ersten echten Einsatz (ROADMAP.md) erfüllt sind.
WARNUNG = """> **Achtung:** Meldi hat noch keine Zugangsprüfung. Jedes Gerät im WLAN oder VPN kann alle Nachrichten, Aufnahmen und
> Fotos lesen. Diese Version ist nur für Tests und Übungen ohne echte Einsatzdaten gedacht."""
INSTALLATION = """## Installation

ZIP herunterladen, entpacken und `installieren.cmd` starten. Details stehen in `docs/betrieb.md`."""


def pep440(version: str) -> str:
    """So schreibt uv die Version in uv.lock: aus 0.2.0-rc.1 wird 0.2.0rc1."""
    return version.replace("-rc.", "rc")


def lies_version(wurzel: Path = ROOT) -> str:
    return tomllib.loads((wurzel / "backend" / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def changelog_abschnitt(text: str, titel: str) -> str | None:
    """Inhalt unter der Überschrift „## titel …“, oder None, wenn es sie nicht gibt."""
    treffer = re.search(rf"^## {re.escape(titel)}(?: .*)?$", text, re.MULTILINE)
    if treffer is None:
        return None
    folgende = re.search(r"^## ", text[treffer.end():], re.MULTILINE)
    ende = treffer.end() + folgende.start() if folgende else len(text)
    return text[treffer.end():ende].strip()


def pruefe_tag(tag: str, wurzel: Path = ROOT) -> list[str]:
    if not tag.startswith("v") or not VERSION_MUSTER.fullmatch(tag[1:]):
        return [f"{tag}: erwartet wird vX.Y.Z oder vX.Y.Z-rc.N"]
    version = tag[1:]
    fehler = []
    if lies_version(wurzel) != version:
        fehler.append(f"backend/pyproject.toml: Version ist {lies_version(wurzel)}, Tag ist {version}")

    paket = json.loads((wurzel / "frontend" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((wurzel / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    for name, gefunden in (
        ("frontend/package.json", paket["version"]),
        ("frontend/package-lock.json", lock["version"]),
        ("frontend/package-lock.json (packages)", lock["packages"][""]["version"]),
    ):
        if gefunden != version:
            fehler.append(f"{name}: Version ist {gefunden}, Tag ist {version}")

    uv_lock = (wurzel / "backend" / "uv.lock").read_text(encoding="utf-8")
    eintrag = re.search(r'^name = "meldi"\nversion = "([^"]*)"', uv_lock, re.MULTILINE)
    if eintrag is None or eintrag.group(1) != pep440(version):
        fehler.append(f"backend/uv.lock: passt nicht zu {pep440(version)}, `uv lock` ausführen")

    changelog = (wurzel / "CHANGELOG.md").read_text(encoding="utf-8")
    if not changelog_abschnitt(changelog, version):
        fehler.append(f"CHANGELOG.md: kein Abschnitt oder kein Inhalt für {version}")
    return fehler


def release_notizen(tag: str, wurzel: Path = ROOT) -> str:
    changelog = (wurzel / "CHANGELOG.md").read_text(encoding="utf-8")
    abschnitt = changelog_abschnitt(changelog, tag[1:])
    if not abschnitt:
        raise SystemExit(f"CHANGELOG.md: kein Inhalt für {tag[1:]}")
    return f"{WARNUNG}\n\n{abschnitt}\n\n{INSTALLATION}\n"


def schliesse_changelog(text: str, version: str, datum: str) -> str:
    inhalt = changelog_abschnitt(text, "Unveröffentlicht")
    if inhalt is None:
        raise SystemExit(f"CHANGELOG.md: Überschrift „{UNVEROEFFENTLICHT}“ fehlt")
    if not inhalt:
        # Ein Kandidat wird unverändert zur stabilen Version, dann gibt es nichts Neues zu notieren.
        if "-rc." in version or not re.search(rf"^## {re.escape(version)}-rc\.\d+", text, re.MULTILINE):
            raise SystemExit("CHANGELOG.md: Der Abschnitt „Unveröffentlicht“ ist leer")
        inhalt = "Keine Änderungen seit dem letzten Release-Kandidaten."
    kopf = text[:text.index(UNVEROEFFENTLICHT)]
    rest_start = text.index(UNVEROEFFENTLICHT) + len(UNVEROEFFENTLICHT)
    folgende = re.search(r"^## ", text[rest_start:], re.MULTILINE)
    rest = text[rest_start + folgende.start():] if folgende else ""
    return f"{kopf}{UNVEROEFFENTLICHT}\n\n## {version} ({datum})\n\n{inhalt}\n" + (f"\n{rest}" if rest else "")


def setze_version(version: str, wurzel: Path = ROOT) -> None:
    if not VERSION_MUSTER.fullmatch(version):
        raise SystemExit(f"{version}: erwartet wird X.Y.Z oder X.Y.Z-rc.N")

    changelog = wurzel / "CHANGELOG.md"
    neu = schliesse_changelog(changelog.read_text(encoding="utf-8"), version, datetime.date.today().isoformat())

    pyproject = wurzel / "backend" / "pyproject.toml"
    text, anzahl = re.subn(
        r'^version = "[^"]*"', f'version = "{version}"', pyproject.read_text(encoding="utf-8"), count=1, flags=re.MULTILINE
    )
    if anzahl != 1:
        raise SystemExit("backend/pyproject.toml: keine Version gefunden")
    pyproject.write_text(text, encoding="utf-8")
    changelog.write_text(neu, encoding="utf-8")

    for name in ("package.json", "package-lock.json"):
        datei = wurzel / "frontend" / name
        daten = json.loads(datei.read_text(encoding="utf-8"))
        daten["version"] = version
        if "packages" in daten:
            daten["packages"][""]["version"] = version
        datei.write_text(json.dumps(daten, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def pruefe_paketnamen(namen: list[str]) -> list[str]:
    """Letzte Sperre vor der Veröffentlichung. Namen ohne den Ordner meldi-<version>/ am Anfang."""
    fehler = []
    for name in namen:
        pfad = Path(name)
        if pfad.name == ".env" or pfad.name.startswith(".env.") or pfad.suffix.lower() in VERBOTENE_ENDUNGEN:
            fehler.append(f"{name}: darf nicht ins Paket")
        elif VERBOTENE_ORDNER.intersection(pfad.parts):
            fehler.append(f"{name}: Ordner darf nicht ins Paket")
    fehler.extend(f"{name}: fehlt im Paket" for name in PFLICHT if name not in namen)
    return fehler


def lade(download: Download, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    datei = cache / f"{download.sha256[:16]}-{download.url.rsplit('/', 1)[1]}"
    if not datei.is_file():
        print(f"Lade {download.url}", flush=True)
        with urllib.request.urlopen(download.url, timeout=120) as antwort:
            datei.write_bytes(antwort.read())
    if hashlib.sha256(datei.read_bytes()).hexdigest() != download.sha256:
        datei.unlink()
        raise SystemExit(f"Falsche Prüfsumme: {download.url}")
    return datei


def versionierte_dateien(wurzel: Path) -> list[str]:
    ausgabe = subprocess.run(["git", "ls-files", "-z"], cwd=wurzel, check=True, capture_output=True).stdout
    alle = [name for name in ausgabe.decode("utf-8").split("\0") if name]
    return [n for n in alle if any(n == v or (v.endswith("/") and n.startswith(v)) for v in VERSIONIERT)]


def bauen(ausgabe: Path, wurzel: Path = ROOT, cache: Path | None = None) -> Path:
    dist = wurzel / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("frontend/dist fehlt, zuerst `npm run build` in frontend/ ausführen")

    version = lies_version(wurzel)
    wurzelname = f"meldi-{version}"
    ausgabe.mkdir(parents=True, exist_ok=True)
    ziel = ausgabe / f"{wurzelname}-windows-x64.zip"
    cache = cache or ausgabe / ".cache"

    namen: list[str] = []
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as paket:
        def schreibe(name: str, daten: bytes) -> None:
            namen.append(name)
            paket.writestr(f"{wurzelname}/{name}", daten)

        for name in versionierte_dateien(wurzel):
            schreibe(name, (wurzel / name).read_bytes())
        for datei in sorted(p for p in dist.rglob("*") if p.is_file()):
            schreibe(f"frontend/dist/{datei.relative_to(dist).as_posix()}", datei.read_bytes())

        schreibe("VERSION", f"{version}\n".encode())
        schreibe("backend/.python-version", f"{PYTHON_VERSION}\n".encode())
        # cmd.exe braucht CRLF, sonst verrutschen Sprungmarken. Im Repository steht die Datei mit LF.
        cmd = (wurzel / "deploy" / "installieren.cmd").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        schreibe("installieren.cmd", cmd)

        for download in WERKZEUGE:
            datei = lade(download, cache)
            if "" in download.inhalt:
                schreibe(download.inhalt[""], datei.read_bytes())
                continue
            with zipfile.ZipFile(datei) as archiv:
                for mitglied, name in download.inhalt.items():
                    schreibe(name, archiv.read(mitglied))

    if fehler := pruefe_paketnamen(namen):
        ziel.unlink()
        raise SystemExit("\n".join(fehler))
    print(f"{ziel} ({ziel.stat().st_size / 1024 / 1024:.0f} MB, {len(namen)} Dateien)")
    return ziel


def _soll(bedingung: object, text: str) -> None:
    if not bedingung:
        raise SystemExit(f"Rauchtest fehlgeschlagen: {text}")


def _installiere(quelle: Path, ziel: Path, *argumente: str) -> None:
    # /s mit äußerem Anführungszeichenpaar: Sonst zerlegt cmd.exe Pfade mit Leerzeichen.
    zusatz = " ".join(argumente)
    befehl = f'cmd.exe /d /s /c ""{quelle / "installieren.cmd"}" -Ziel "{ziel}" -Still -OhneModell {zusatz}"'
    umgebung = {k: v for k, v in os.environ.items() if k not in {"VIRTUAL_ENV", "UV_PYTHON"}}
    ergebnis = subprocess.run(befehl, env=umgebung)
    _soll(ergebnis.returncode == 0, f"Installer endete mit Code {ergebnis.returncode}")


def _pruefe_laufende_app(ziel: Path) -> None:
    backend = ziel / "aktiv" / "backend"
    python = backend / ".venv" / "Scripts" / "python.exe"
    module = "tkinter, customtkinter, av, faster_whisper, ctranslate2, app.main, app.starter.fenster"
    subprocess.run([str(python), "-c", f"import {module}"], cwd=backend, check=True)
    entwicklung = subprocess.run([str(python), "-c", "import pytest"], cwd=backend, capture_output=True)
    _soll(entwicklung.returncode != 0, "Entwicklungspakete sind mitinstalliert")

    deploy = ziel / "aktiv" / "deploy"
    subprocess.run([str(deploy / "bin" / "caddy.exe"), "validate", "--config", str(deploy / "Caddyfile")], check=True)

    port = 8765
    umgebung = {**os.environ, "MELDI_STT_ENABLED": "false", "MELDI_COOKIE_SECURE": "false"}
    server = subprocess.Popen(
        [str(python), "-m", "uvicorn", "--factory", "app.main:create_app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=backend, env=umgebung,
    )
    ohne_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        gesundheit = None
        frist = time.monotonic() + 120
        while time.monotonic() < frist and gesundheit is None:
            _soll(server.poll() is None, "Server ist abgestürzt")
            try:
                with ohne_proxy.open(f"http://127.0.0.1:{port}/api/health", timeout=2) as antwort:
                    gesundheit = json.loads(antwort.read())
            except OSError:
                time.sleep(1)
        _soll(gesundheit and gesundheit.get("ok"), "/api/health antwortet nicht")
        with ohne_proxy.open(f"http://127.0.0.1:{port}/", timeout=5) as antwort:
            _soll(b"/assets/" in antwort.read(), "Startseite enthält das Frontend nicht")
    finally:
        server.terminate()
        server.wait(30)
    _soll((ziel / "data" / "meldi.db").is_file(), "Die Datenbank liegt nicht im Datenordner")


def rauchtest(zip_datei: Path) -> None:
    """Prüft das ausgelieferte Paket: Erstinstallation, Update mit Sicherung, Serverstart, Rückweg."""
    if os.name != "nt":
        raise SystemExit("Der Rauchtest läuft nur unter Windows")

    # Kurzer Pfad wegen MAX_PATH, Leerzeichen und Umlaut decken die Quoting-Fehler auf.
    basis = Path(tempfile.mkdtemp(prefix="mä l", dir=os.environ.get("RUNNER_TEMP") or None))
    with zipfile.ZipFile(zip_datei) as paket:
        paket.extractall(basis / "q")
    neu = next((basis / "q").iterdir())
    version = (neu / "VERSION").read_text(encoding="utf-8").strip()
    ziel = basis / "z"

    # Eine „ältere Version“ mit kürzerer Migrationskette, damit der Rückweg die Datenbank zurückspielen muss.
    alt_version = "0.0.1-rauchtest"
    alt = basis / "a" / f"meldi-{alt_version}"
    shutil.copytree(neu, alt)
    (alt / "VERSION").write_text(f"{alt_version}\n", encoding="utf-8")
    sorted((alt / "backend" / "alembic" / "versions").glob("*.py"))[-1].unlink()

    print("\n=== Erstinstallation ===", flush=True)
    _installiere(alt, ziel)
    def aktive() -> str:
        return (ziel / "aktiv" / "VERSION").read_text(encoding="utf-8").strip()

    _soll(aktive() == alt_version, "Die erste Version ist nicht aktiv")

    einsatz = ziel / "data" / "einsaetze" / "rauchtest"
    (einsatz / "vorlaeufig").mkdir(parents=True)
    (einsatz / "meldi.db").write_bytes(b"alt")
    (einsatz / "vorlaeufig" / "nie-abgesendet.bin").write_bytes(b"x")

    print("\n=== Update ===", flush=True)
    _installiere(neu, ziel)
    _soll(aktive() == version, "Die neue Version ist nicht aktiv")
    sicherung = ziel / "data" / "sicherung" / alt_version / "einsaetze" / "rauchtest"
    _soll((sicherung / "meldi.db").read_bytes() == b"alt", "Die Datenbank wurde nicht gesichert")
    _soll(not (sicherung / "vorlaeufig").exists(), "Vorläufige Uploads gehören nicht in die Sicherung")

    print("\n=== Serverstart ===", flush=True)
    _pruefe_laufende_app(ziel)

    print("\n=== Rückweg ===", flush=True)
    (einsatz / "meldi.db").write_bytes(b"neu")
    _installiere(neu, ziel, "-Zurueck")
    _soll(aktive() == alt_version, "Der Rückweg hat die Version nicht umgestellt")
    _soll((einsatz / "meldi.db").read_bytes() == b"alt", "Der Rückweg hat die Datenbank nicht zurückgespielt")
    aufgehoben = list((ziel / "data" / "sicherung").glob("vor-rueckweg-*/rauchtest/meldi.db"))
    _soll(aufgehoben and aufgehoben[0].read_bytes() == b"neu", "Der neuere Stand wurde nicht aufgehoben")
    print("\nRauchtest bestanden")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    befehle = parser.add_subparsers(dest="befehl", required=True)
    befehle.add_parser("setze-version").add_argument("version")
    befehle.add_parser("pruefe-tag").add_argument("tag")
    notizen = befehle.add_parser("notizen")
    notizen.add_argument("tag")
    notizen.add_argument("datei", type=Path)
    befehle.add_parser("bauen").add_argument("--ausgabe", type=Path, default=ROOT / "paket")
    befehle.add_parser("rauchtest").add_argument("zip", type=Path)
    args = parser.parse_args()

    if args.befehl == "setze-version":
        setze_version(args.version)
        uv = shutil.which("uv")
        if uv is None:
            raise SystemExit("uv nicht gefunden, `uv lock` in backend/ von Hand ausführen")
        subprocess.run([uv, "lock"], cwd=ROOT / "backend", check=True)
    elif args.befehl == "pruefe-tag":
        fehler = pruefe_tag(args.tag)
        for eintrag in fehler:
            print(eintrag, file=sys.stderr)
        return 1 if fehler else 0
    elif args.befehl == "notizen":
        args.datei.write_text(release_notizen(args.tag), encoding="utf-8")
    elif args.befehl == "bauen":
        bauen(args.ausgabe)
    elif args.befehl == "rauchtest":
        rauchtest(args.zip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
