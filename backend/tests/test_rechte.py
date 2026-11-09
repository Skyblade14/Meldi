"""Rechte je Endpunkt und Rolle, außerdem Einsatzgrenzen, abgelaufene Sitzungen und Gleichzeitigkeit."""

import importlib
import pkgutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocketDisconnect

import app.api
from app.db import new_session, utcnow
from app.models import Anmeldung, Einsatz, Nachricht
from app.schemas.message import NachrichtCreate
from app.services import message_service
from app.services.seed import neuer_einsatz

ALLE = {"ohne", "melder", "elw", "beobachter"}
ANGEMELDET = {"melder", "elw", "beobachter"}
MELDEN = {"melder", "elw"}
LESEN = {"elw", "beobachter"}
ELW = {"elw"}

# Neuer Endpunkt? Hier eintragen, sonst scheitert test_jeder_endpunkt_steht_in_der_matrix.
MATRIX: dict[tuple[str, str], set[str]] = {
    ("GET", "/api/health"): ALLE,
    ("GET", "/api/auth/funktionen"): ALLE,
    ("POST", "/api/auth/login"): ALLE,
    ("GET", "/api/auth/me"): ANGEMELDET,
    ("POST", "/api/auth/logout"): ANGEMELDET,
    ("GET", "/api/auth/anmeldungen"): ELW,
    ("POST", "/api/messages"): MELDEN,
    ("GET", "/api/messages"): ANGEMELDET,
    ("GET", "/api/messages/{nachricht_id}"): LESEN,
    ("GET", "/api/messages/{nachricht_id}/audit"): LESEN,
    ("PUT", "/api/messages/{nachricht_id}/status"): ELW,
    ("GET", "/api/messages/{nachricht_id}/anhaenge/{anhang_id}"): LESEN,
    ("GET", "/api/speech/status"): ANGEMELDET,
    ("POST", "/api/speech/transcribe"): MELDEN,
    ("POST", "/api/uploads/foto"): MELDEN,
}
WEBSOCKETS: dict[str, set[str]] = {"/api/ws/elw": LESEN}

FUNKTION = {"melder": "EA Brand", "elw": "ELW", "beobachter": None}
NACHRICHT = {"an": "ELW", "inhalt": "Lage stabil"}


def _anmelden(c: TestClient, name: str, rolle: str) -> TestClient:
    r = c.post("/api/auth/login", json={"name": name, "rolle": rolle, "funktion": FUNKTION[rolle]})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def client_als(app):
    def erstelle(rolle: str) -> TestClient:
        c = TestClient(app)
        return c if rolle == "ohne" else _anmelden(c, f"Person {rolle}", rolle)

    return erstelle


@pytest.fixture
def nachricht_id(melder) -> int:
    return melder.post("/api/messages", json=NACHRICHT).json()["id"]


def test_jeder_endpunkt_steht_in_der_matrix():
    # Alle Router-Module, damit auch ein neues Modul auffällt, das noch nirgends eingebunden ist.
    module = [importlib.import_module(f"app.api.{m.name}") for m in pkgutil.iter_modules(app.api.__path__)]
    routen = [r for m in module if hasattr(m, "router") for r in m.router.routes]
    vorhanden = {(m, r.path) for r in routen if isinstance(r, APIRoute) for m in r.methods}
    assert vorhanden == set(MATRIX)
    assert {r.path for r in routen if isinstance(r, WebSocketRoute)} == set(WEBSOCKETS)


@pytest.mark.parametrize("rolle", sorted(ALLE))
@pytest.mark.parametrize(("methode", "pfad"), sorted(MATRIX), ids=lambda x: x.replace("/api/", ""))
def test_rechtematrix(client_als, nachricht_id, methode, pfad, rolle):
    url = pfad.format(nachricht_id=nachricht_id, anhang_id=999)
    status = client_als(rolle).request(methode, url).status_code
    if rolle in MATRIX[methode, pfad]:
        assert status not in (401, 403)  # 404 oder 422 sind hier richtig: Die Anfrage ist bewusst leer
    else:
        assert status == (401 if rolle == "ohne" else 403)


@pytest.mark.parametrize("rolle", sorted(ALLE))
@pytest.mark.parametrize("pfad", sorted(WEBSOCKETS))
def test_rechtematrix_websocket(client_als, pfad, rolle):
    c = client_als(rolle)
    if rolle in WEBSOCKETS[pfad]:
        with c.websocket_connect(pfad):
            pass
    else:
        with pytest.raises(WebSocketDisconnect), c.websocket_connect(pfad):
            pass


# --- Einsatzgrenzen ---


@pytest.fixture
def anderer_einsatz(app, elw, nachricht_id):
    """Bisheriger Einsatz mit Nachricht, danach ein neuer Einsatz mit eigener ELW-Anmeldung."""
    with new_session() as db:
        neuer_einsatz(db, "Zweiter Einsatz")
    return _anmelden(TestClient(app), "ELW Zwei", "elw")


@pytest.mark.parametrize(
    ("methode", "pfad"),
    [("GET", ""), ("GET", "/audit"), ("PUT", "/status"), ("GET", "/anhaenge/1")],
)
def test_kein_zugriff_ueber_die_einsatzgrenze(anderer_einsatz, nachricht_id, methode, pfad):
    r = anderer_einsatz.request(
        methode, f"/api/messages/{nachricht_id}{pfad}", json={"status": "erledigt"} if methode == "PUT" else None
    )
    assert r.status_code == 404


def test_liste_nur_aus_dem_eigenen_einsatz(anderer_einsatz):
    assert anderer_einsatz.get("/api/messages").json() == []


def test_live_nur_aus_dem_eigenen_einsatz(elw, anderer_einsatz):
    """elw gehört zum alten Einsatz, anderer_einsatz meldet in den neuen."""
    with elw.websocket_connect("/api/ws/elw") as ws:
        anderer_einsatz.post("/api/messages", json={**NACHRICHT, "inhalt": "Zweiter Einsatz"})
        n = elw.post("/api/messages", json={**NACHRICHT, "inhalt": "Erster Einsatz"}).json()
        event = ws.receive_json()
    assert event["nachricht"]["id"] == n["id"]


# --- Abgelaufene Sitzung ---


def _ablaufen_lassen(*, name: str | None = None) -> None:
    with new_session() as db:
        for a in db.query(Anmeldung).all():
            if name is None or a.user.name == name:
                a.gueltig_bis = utcnow() - timedelta(minutes=1)
        db.commit()


def test_abgelaufene_sitzung_wird_abgewiesen(melder, elw):
    _ablaufen_lassen()
    assert melder.get("/api/auth/me").status_code == 401
    assert melder.post("/api/messages", json=NACHRICHT).status_code == 401
    assert elw.get("/api/messages").status_code == 401
    with pytest.raises(WebSocketDisconnect), elw.websocket_connect("/api/ws/elw"):
        pass


# --- Live-Kanal nach dem Ende der Anmeldung (F1) ---


def test_live_kanal_endet_mit_abmeldung(elw, melder):
    with elw.websocket_connect("/api/ws/elw") as ws:
        elw.post("/api/auth/logout")
        melder.post("/api/messages", json=NACHRICHT)
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_live_kanal_endet_mit_neuer_anmeldung(elw, melder):
    with elw.websocket_connect("/api/ws/elw") as ws:
        _anmelden(elw, "Anderer Name", "elw")
        melder.post("/api/messages", json=NACHRICHT)
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_live_kanal_endet_mit_ablauf(elw, beobachter, melder):
    with elw.websocket_connect("/api/ws/elw") as ws, beobachter.websocket_connect("/api/ws/elw") as ws2:
        _ablaufen_lassen(name="ELW")
        melder.post("/api/messages", json=NACHRICHT)
        assert ws2.receive_json()["type"] == "nachricht.neu"  # gültige Anmeldungen laufen weiter
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


# --- Gleichzeitigkeit ---


def _parallel(aufgabe, anzahl: int) -> list:
    start = threading.Barrier(anzahl)

    def lauf(i: int):
        start.wait()
        return aufgabe(i)

    with ThreadPoolExecutor(anzahl) as pool:
        return list(pool.map(lauf, range(anzahl)))


def _melde(anmeldung_id: int, inhalt: str, sende_id: str | None = None) -> tuple[int, bool]:
    with new_session() as db:
        ergebnis = message_service.create_nachricht(
            db, db.get(Anmeldung, anmeldung_id), NachrichtCreate(an="ELW", inhalt=inhalt, sende_id=sende_id)
        )
        return ergebnis.nachricht.lfd_nr, ergebnis.neu


def _anmeldung_id() -> int:
    with new_session() as db:
        return db.query(Anmeldung).one().id


def test_parallele_meldungen_bekommen_lueckenlose_nummern(melder):
    aid = _anmeldung_id()
    nummern = _parallel(lambda i: _melde(aid, f"Meldung {i}")[0], 12)
    assert sorted(nummern) == list(range(1, 13))
    with new_session() as db:
        einsatz = db.query(Einsatz).filter(Einsatz.ende.is_(None)).one()
        assert einsatz.naechste_lfd_nr == 13


def test_parallele_gleiche_sende_id_ergibt_eine_nachricht(melder):
    aid = _anmeldung_id()
    ergebnisse = _parallel(lambda _: _melde(aid, "Einmal bitte", "a" * 32), 8)
    assert sum(neu for _, neu in ergebnisse) == 1
    assert {nr for nr, _ in ergebnisse} == {1}
    with new_session() as db:
        assert db.query(Nachricht).count() == 1
