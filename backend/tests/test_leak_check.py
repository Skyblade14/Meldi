"""Die Prüfung, die sensible Dateien und Adressen aus dem öffentlichen Repository fernhält."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "leak_check", Path(__file__).resolve().parents[2] / "tools" / "leak_check.py"
)
leak_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(leak_check)


def ip(*teile: int) -> str:
    """Setzt Adressen erst zur Laufzeit zusammen, sonst schlüge die Prüfung bei dieser Datei selbst an."""
    return ".".join(map(str, teile))


def befunde(tmp_path, name: str, inhalt: str | bytes, begriffe: list[str] | None = None) -> list[str]:
    pfad = tmp_path / name
    pfad.write_bytes(inhalt if isinstance(inhalt, bytes) else inhalt.encode())
    return leak_check.pruefe_datei(pfad, begriffe or [])


@pytest.mark.parametrize("adresse", [ip(100, 64, 0, 1), ip(100, 127, 255, 254), ip(8, 8, 8, 8)])
def test_tailscale_und_oeffentliche_adressen_fallen_auf(tmp_path, adresse):
    ergebnis = befunde(tmp_path, "a.md", f"Text\nhttps://{adresse}:8443/melder/\n")
    assert len(ergebnis) == 1
    assert ergebnis[0].endswith(":2: öffentliche oder Tailscale-Adresse")


def test_befund_nennt_die_adresse_nicht(tmp_path):
    """Die Logs von GitHub Actions sind öffentlich."""
    adresse = ip(100, 64, 0, 1)
    assert adresse not in befunde(tmp_path, "a.md", adresse)[0]


@pytest.mark.parametrize(
    "text",
    [ip(127, 0, 0, 1), ip(192, 168, 8, 10), ip(10, 0, 0, 5), ip(0, 0, 0, 0), ip(192, 0, 2, 1), "1.2.3.4.5", "999.1.1.1"],
)
def test_harmlose_adressen_und_versionen_bleiben_erlaubt(tmp_path, text):
    assert befunde(tmp_path, "a.md", text) == []


@pytest.mark.parametrize(
    "inhalt",
    [b"SQLite format 3\0\x10\0", b"\xff\xd8\xff\xe0\0\x10JFIF", b"\x1aE\xdf\xa3\x01\0\0\0"],
    ids=["datenbank", "foto", "aufnahme"],
)
def test_binaerdateien_fallen_auch_mit_harmloser_endung_auf(tmp_path, inhalt):
    assert "Binärdatei" in befunde(tmp_path, "umbenannt.txt", inhalt)[0]


def test_zu_grosse_datei_faellt_auf(tmp_path):
    assert "größer als" in befunde(tmp_path, "export.csv", "x" * (leak_check.MAX_BYTES + 1))[0]


@pytest.mark.parametrize("name", [".env", ".env.local", "server.key", "ca.crt", "ROOT.PEM"])
def test_schluessel_und_umgebungsdateien_fallen_auf(tmp_path, name):
    assert "Schlüssel" in befunde(tmp_path, name, "x")[0]


def test_env_beispiel_bleibt_erlaubt(tmp_path):
    assert befunde(tmp_path, ".env.example", "MELDI_X=1") == []


def test_lokale_begriffe_ohne_gross_und_kleinschreibung(tmp_path):
    ergebnis = befunde(tmp_path, "a.md", "ok\nBei Familie MUSTER\n", ["muster"])
    assert len(ergebnis) == 1
    assert ":2:" in ergebnis[0]
    assert "MUSTER" not in ergebnis[0]
