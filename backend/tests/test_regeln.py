"""Die unverhandelbaren Regeln aus CLAUDE.md, maschinell geprüft."""

import ast
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import BACKEND_DIR, PROJECT_DIR

FRONTEND = PROJECT_DIR / "frontend"
DIST = FRONTEND / "dist"
APP = BACKEND_DIR / "app"

CSP = (
    "default-src 'self'; connect-src 'self' ws://testserver wss://testserver; img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
)

# Kommen in gebündelten Bibliotheken als Kennungen oder Links in Fehlertexten vor, werden aber nie aufgerufen.
ERLAUBTE_URLS = re.compile(r"https?://(www\.w3\.org/|vuejs\.org|vue-i18n\.intlify\.dev|github\.com/vuejs|github\.com/MikeKovarik/exifr|ns\.adobe\.com|purl\.org|cipa\.jp)")


def _imports(pfad: Path) -> set[str]:
    module: set[str] = set()
    for knoten in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
        if isinstance(knoten, ast.Import):
            module |= {a.name for a in knoten.names}
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            module.add(knoten.module)
    return module


def test_csp_ist_exakt_festgeschrieben(app):
    with TestClient(app) as c:
        assert c.get("/api/health").headers["content-security-policy"] == CSP


def test_csp_nimmt_keinen_manipulierten_host_auf(app):
    with TestClient(app) as c:
        csp = c.get("/api/health", headers={"Host": "boese.example; script-src *"}).headers["content-security-policy"]
    assert "boese" not in csp and "script-src" not in csp
    assert "connect-src 'self';" in csp


def test_csp_gilt_auch_fuer_die_seiten(app):
    with TestClient(app) as c:
        assert c.get("/elw/").headers["content-security-policy"] == CSP


def test_mikrofon_nur_fuer_die_eigene_seite(app):
    with TestClient(app) as c:
        assert c.get("/api/health").headers["permissions-policy"] == "microphone=(self), camera=(), geolocation=()"


@pytest.mark.parametrize("pfad", ["/api/health", "/api/auth/funktionen", "/api/auth/me", "/api/gibtsnicht"])
def test_api_antworten_werden_nie_gecacht(app, pfad):
    with TestClient(app) as c:
        assert c.get(pfad).headers["cache-control"] == "no-store"


def test_keine_externen_urls_im_gebauten_frontend():
    if not DIST.is_dir():
        pytest.skip("frontend/dist fehlt")
    funde = [
        f"{datei.relative_to(DIST)}: {treffer}"
        for datei in DIST.rglob("*")
        if datei.suffix in {".html", ".js", ".css", ".map"}
        for treffer in re.findall(r"https?://[^\s\"'`)<>]+", datei.read_text(encoding="utf-8"))
        if not ERLAUBTE_URLS.match(treffer)
    ]
    assert funde == []


def _frontend_quellen() -> list[Path]:
    return [p for p in (FRONTEND / "src").rglob("*") if p.suffix in {".ts", ".vue"} and not p.name.endswith(".test.ts")]


@pytest.mark.parametrize("verboten", ["SpeechRecognition", "localStorage", "sessionStorage", "indexedDB", "serviceWorker"])
def test_verbotene_browser_apis_nicht_im_quellcode(verboten):
    assert [p.name for p in _frontend_quellen() if verboten in p.read_text(encoding="utf-8")] == []


def test_aufnahme_bleibt_roh():
    """Mit Echounterdrückung liefert Android Telefonie-Audio, die Erkennung bricht ein."""
    quelle = (FRONTEND / "src/shared/useRecorder.ts").read_text(encoding="utf-8")
    assert "roh: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }" in quelle


@pytest.mark.parametrize(
    ("paket", "verboten"),
    [
        ("stt", ("app.api", "app.services", "app.models", "app.db", "fastapi")),
        ("starter", ("app.api", "app.services", "app.models", "app.db", "fastapi", "sqlalchemy")),
        ("models", ("app.api", "app.services", "app.stt")),
        ("services", ("app.api",)),
    ],
)
def test_abhaengigkeitsrichtung(paket, verboten):
    funde = [
        f"{datei.relative_to(APP)}: {modul}"
        for datei in (APP / paket).rglob("*.py")
        for modul in _imports(datei)
        if modul.startswith(verboten)
    ]
    assert funde == []
