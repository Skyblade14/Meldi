"""Paketbau und Release-Vorbereitung. Installer und Windows-Abläufe prüft der Rauchtest in release.yml."""

import importlib.util
import json
import re
import sys
import zipfile
from pathlib import Path

import pytest

from app.config import PROJECT_DIR, installierte_version

spec = importlib.util.spec_from_file_location("paket", PROJECT_DIR / "tools" / "paket.py")
paket = importlib.util.module_from_spec(spec)
sys.modules["paket"] = paket  # dataclass sucht das Modul dort
spec.loader.exec_module(paket)

CHANGELOG = "# Änderungen\n\n## Unveröffentlicht\n\n- Neu\n\n## 0.1.0 (2026-01-01)\n\n- Alt\n"


def projekt(wurzel: Path, version: str = "0.2.0-rc.1", changelog: str | None = None) -> Path:
    (wurzel / "backend").mkdir(parents=True)
    (wurzel / "frontend").mkdir()
    (wurzel / "backend" / "pyproject.toml").write_text(
        f'[project]\nname = "meldi"\nversion = "{version}"\n\n[tool.x]\nversion = "bleibt"\n', encoding="utf-8"
    )
    (wurzel / "backend" / "uv.lock").write_text(
        f'[[package]]\nname = "meldi"\nversion = "{paket.pep440(version)}"\n', encoding="utf-8"
    )
    (wurzel / "frontend" / "package.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (wurzel / "frontend" / "package-lock.json").write_text(
        json.dumps({"version": version, "packages": {"": {"version": version}}}), encoding="utf-8"
    )
    inhalt = changelog if changelog is not None else f"# Änderungen\n\n## {version} (2026-11-09)\n\n- Neu\n"
    (wurzel / "CHANGELOG.md").write_text(inhalt, encoding="utf-8")
    return wurzel


def test_passendes_tag_hat_keine_fehler(tmp_path):
    assert paket.pruefe_tag("v0.2.0-rc.1", projekt(tmp_path)) == []


@pytest.mark.parametrize("tag", ["0.2.0", "v0.2", "v0.2.0-beta", "v0.2.0-rc.1;rm", "v10.0.0.1"])
def test_falsches_tagformat(tmp_path, tag):
    assert "erwartet" in paket.pruefe_tag(tag, projekt(tmp_path))[0]


def test_tag_muss_zur_version_passen(tmp_path):
    fehler = paket.pruefe_tag("v0.3.0", projekt(tmp_path))
    assert any("pyproject" in f for f in fehler) and any("package.json" in f for f in fehler)
    assert any("uv.lock" in f for f in fehler) and any("CHANGELOG" in f for f in fehler)


def test_leerer_changelog_abschnitt_blockiert(tmp_path):
    wurzel = projekt(tmp_path, changelog="## 0.2.0-rc.1 (2026-11-09)\n\n## 0.1.0\n\n- Alt\n")
    assert any("CHANGELOG" in f for f in paket.pruefe_tag("v0.2.0-rc.1", wurzel))


def test_notizen_enthalten_warnung_und_nur_den_eigenen_abschnitt(tmp_path):
    wurzel = projekt(tmp_path, changelog="## 0.2.0-rc.1 (2026-11-09)\n\n- Neu\n\n## 0.1.0 (2026-01-01)\n\n- Alt\n")
    notizen = paket.release_notizen("v0.2.0-rc.1", wurzel)
    assert "keine Zugangsprüfung" in notizen and "- Neu" in notizen and "- Alt" not in notizen


def test_setze_version_aendert_alle_manifeste(tmp_path):
    wurzel = projekt(tmp_path, version="0.1.0", changelog=CHANGELOG)
    paket.setze_version("0.2.0-rc.1", wurzel)

    pyproject = (wurzel / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.2.0-rc.1"' in pyproject and 'version = "bleibt"' in pyproject
    lock = json.loads((wurzel / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["version"] == lock["packages"][""]["version"] == "0.2.0-rc.1"
    changelog = (wurzel / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(r"## Unveröffentlicht\n\n## 0\.2\.0-rc\.1 \(\d{4}-\d{2}-\d{2}\)\n\n- Neu\n\n## 0\.1\.0", changelog)


def test_leerer_changelog_blockiert_das_setzen(tmp_path):
    wurzel = projekt(tmp_path, version="0.1.0", changelog="## Unveröffentlicht\n\n## 0.1.0\n\n- Alt\n")
    with pytest.raises(SystemExit, match="leer"):
        paket.setze_version("0.2.0", wurzel)
    assert 'version = "0.1.0"' in (wurzel / "backend" / "pyproject.toml").read_text(encoding="utf-8")


def test_kandidat_wird_ohne_neue_eintraege_stabil():
    text = "## Unveröffentlicht\n\n## 0.2.0-rc.1 (2026-11-09)\n\n- Neu\n"
    neu = paket.schliesse_changelog(text, "0.2.0", "2026-11-10")
    assert "## 0.2.0 (2026-11-10)\n\nKeine Änderungen" in neu and "- Neu" in neu


def test_vollstaendige_paketnamen_sind_erlaubt():
    assert paket.pruefe_paketnamen([*paket.PFLICHT, "frontend/dist/assets/start.js"]) == []


@pytest.mark.parametrize(
    "name",
    [
        "backend/.env", "backend/.env.local", "data/einsaetze/x/meldi.db", "backend/app/x.pyc", "root.crt",
        "backend/tests/test_api.py", "aufnahme.webm", "backend/.venv/pyvenv.cfg", "foto.JPG",
    ],
)
def test_sensible_dateien_blockieren_das_paket(name):
    assert any(name in f for f in paket.pruefe_paketnamen([*paket.PFLICHT, name]))


def test_fehlende_pflichtdatei_blockiert_das_paket():
    namen = [n for n in paket.PFLICHT if n != "deploy/bin/caddy.exe"]
    assert any("caddy.exe" in f for f in paket.pruefe_paketnamen(namen))


def test_positivliste_laesst_nur_app_dateien_durch():
    namen = paket.versionierte_dateien(PROJECT_DIR)
    assert "backend/app/main.py" in namen and "backend/uv.lock" in namen
    assert not [n for n in namen if n.startswith(("backend/tests/", "tools/", "docs/", ".github/", "frontend/src/"))]


def test_bau_schreibt_version_und_crlf(tmp_path, monkeypatch):
    monkeypatch.setattr(paket, "WERKZEUGE", [])
    monkeypatch.setattr(paket, "PFLICHT", ("VERSION", "installieren.cmd"))
    monkeypatch.setattr(paket, "versionierte_dateien", lambda _: [])
    wurzel = tmp_path / "repo"
    (wurzel / "frontend" / "dist").mkdir(parents=True)
    (wurzel / "deploy").mkdir()
    (wurzel / "backend").mkdir()
    (wurzel / "frontend" / "dist" / "index.html").write_text("<html>", encoding="utf-8")
    (wurzel / "deploy" / "installieren.cmd").write_bytes(b"@echo off\necho hallo\n")
    (wurzel / "backend" / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    (wurzel / "backend" / ".env").write_text("GEHEIM=1\n", encoding="utf-8")

    ziel = paket.bauen(tmp_path / "ausgabe", wurzel)

    assert ziel.name == "meldi-1.2.3-windows-x64.zip"
    with zipfile.ZipFile(ziel) as archiv:
        namen = archiv.namelist()
        assert archiv.read("meldi-1.2.3/VERSION") == b"1.2.3\n"
        assert archiv.read("meldi-1.2.3/backend/.python-version").decode().strip() == paket.PYTHON_VERSION
        assert archiv.read("meldi-1.2.3/installieren.cmd") == b"@echo off\r\necho hallo\r\n"
    assert "meldi-1.2.3/backend/.env" not in namen


def test_falsche_pruefsumme_bricht_ab(tmp_path):
    quelle = tmp_path / "werkzeug.zip"
    quelle.write_bytes(b"manipuliert")
    download = paket.Download(quelle.as_uri(), "0" * 64)
    with pytest.raises(SystemExit, match="Prüfsumme"):
        paket.lade(download, tmp_path / "cache")
    assert not list((tmp_path / "cache").iterdir())


def test_werkzeuge_sind_https_und_gepinnt():
    for download in paket.WERKZEUGE:
        assert download.url.startswith("https://") and "latest" not in download.url
        assert re.fullmatch(r"[0-9a-f]{64}", download.sha256)


@pytest.mark.parametrize("name", ["installieren.ps1", "installieren.cmd"])
def test_installer_ist_ascii(name):
    """PowerShell 5.1 liest Dateien ohne BOM als ANSI, Umlaute würden die Syntax zerstören."""
    (PROJECT_DIR / "deploy" / name).read_bytes().decode("ascii")


def test_installer_nutzt_keine_powershell7_syntax():
    text = (PROJECT_DIR / "deploy" / "installieren.ps1").read_text(encoding="utf-8")
    ohne_kommentare = "\n".join(z for z in text.splitlines() if not z.lstrip().startswith("#"))
    assert not re.search(r"\?\?|\?\.|\|\|| && ", ohne_kommentare)


def test_installierte_version(tmp_path):
    assert installierte_version(tmp_path) is None
    (tmp_path / "VERSION").write_text("0.2.0\n", encoding="utf-8")
    assert installierte_version(tmp_path) == "0.2.0"
