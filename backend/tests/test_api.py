from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import new_session
from app.main import create_app
from app.models import Anmeldung, Einsatz, Nachricht, Status
from app.services import message_service


def nachricht(**kw):
    return {"an": "Einsatzleitung", "inhalt": "Feuer unter Kontrolle", **kw}


def test_login_legt_person_an_und_rolle_kommt_aus_der_anmeldung(app):
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"name": " Neue Person ", "rolle": "melder", "funktion": "EA Brand"})
        assert r.status_code == 200 and r.json()["name"] == "Neue Person"
        assert c.get("/api/auth/me").json()["rolle"] == "melder"
        r = c.post("/api/auth/login", json={"name": "Neue Person", "rolle": "elw", "funktion": "ELW"})
        assert r.status_code == 200 and c.get("/api/auth/me").json()["rolle"] == "elw"


def test_login_funktion_nur_fuer_beobachter_optional(app):
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"name": "A", "rolle": "melder"}).status_code == 422
        r = c.post("/api/auth/login", json={"name": "A", "rolle": "beobachter"})
        assert r.status_code == 200 and r.json()["funktion"] == "Beobachter"


def test_login_ohne_namen_abgewiesen(app):
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"name": "   ", "rolle": "beobachter"}).status_code == 422


def test_login_beendet_bisherige_anmeldung(app, elw):
    with TestClient(app) as c:
        c.post("/api/auth/login", json={"name": "Wechsel", "rolle": "melder", "funktion": "EA Brand"})
        c.post("/api/auth/login", json={"name": "Wechsel", "rolle": "elw", "funktion": "ELW"})
    eintraege = [a for a in elw.get("/api/auth/anmeldungen").json() if a["name"] == "Wechsel"]
    assert [a["rolle"] for a in eintraege] == ["elw"]


def test_anmeldungen_nur_fuer_elw_und_ohne_abgemeldete(app, elw, melder, beobachter):
    assert melder.get("/api/auth/anmeldungen").status_code == 403
    assert beobachter.get("/api/auth/anmeldungen").status_code == 403
    assert {a["name"] for a in elw.get("/api/auth/anmeldungen").json()} == {"ELW", "Melder 1", "Beobachter"}
    melder.post("/api/auth/logout")
    assert {a["name"] for a in elw.get("/api/auth/anmeldungen").json()} == {"ELW", "Beobachter"}


def test_stt_fehler_ergibt_503(melder, stt):
    async def kaputt(audio, hint):
        raise RuntimeError("Modell fehlt")

    stt.transcribe = kaputt
    r = melder.post("/api/speech/transcribe", data={"field": "inhalt"}, files={"audio": ("a.webm", b"x")})
    assert r.status_code == 503


def test_me_und_logout(melder):
    assert melder.get("/api/auth/me").json() == {
        "name": "Melder 1", "rolle": "melder", "funktion": "EA Brand", "einsatz": "Test-Einsatz",
    }
    assert melder.post("/api/auth/logout").status_code == 204
    assert melder.get("/api/auth/me").status_code == 401


def test_ohne_anmeldung_kein_zugriff(app):
    with TestClient(app) as c:
        assert c.get("/api/messages").status_code == 401
        assert c.post("/api/messages", json=nachricht()).status_code == 401
        assert c.post("/api/speech/transcribe", data={"field": "an"}, files={"audio": ("a.webm", b"x")}).status_code == 401


def test_nachricht_wer_an_wen_was_wann(melder):
    r = melder.post("/api/messages", json=nachricht(erfasst_at="2026-11-07T10:00:00+01:00"))
    assert r.status_code == 201
    n = r.json()
    assert n["lfd_nr"] == 1
    assert n["von_funktion"] == "EA Brand"
    assert n["von_name"] == "Melder 1"
    assert n["an"] == "Einsatzleitung"
    assert n["an_funktion_id"] is not None  # bekannte Funktion verknüpft
    assert "prioritaet" not in n
    assert n["status"] == "neu"
    assert n["erfasst_at"].startswith("2026-11-07T09:00:00")  # in UTC
    assert n["eingang_at"].endswith("Z") or "+00:00" in n["eingang_at"]


def test_laufende_nummer_pro_einsatz(melder, melder2):
    nrs = [melder.post("/api/messages", json=nachricht()).json()["lfd_nr"] for _ in range(3)]
    nrs.append(melder2.post("/api/messages", json=nachricht()).json()["lfd_nr"])
    assert nrs == [1, 2, 3, 4]


def test_melder_sieht_nur_eigene(melder, melder2, elw):
    melder.post("/api/messages", json=nachricht(inhalt="von 1"))
    melder2.post("/api/messages", json=nachricht(inhalt="von 2"))
    assert [n["inhalt"] for n in melder.get("/api/messages").json()] == ["von 1"]
    assert [n["inhalt"] for n in elw.get("/api/messages").json()] == ["von 2", "von 1"]


def test_elw_endpunkte_nur_fuer_elw(melder, elw):
    nid = melder.post("/api/messages", json=nachricht()).json()["id"]
    assert melder.get(f"/api/messages/{nid}").status_code == 403
    assert melder.get(f"/api/messages/{nid}/audit").status_code == 403
    assert elw.get(f"/api/messages/{nid}").status_code == 200


def test_audit_bei_erstellung(melder, elw):
    nid = melder.post("/api/messages", json=nachricht()).json()["id"]
    audit = elw.get(f"/api/messages/{nid}/audit").json()
    assert len(audit) == 1
    assert audit[0]["aktion"] == "erstellt"
    assert audit[0]["funktion"] == "EA Brand"
    assert audit[0]["aenderungen"]["inhalt"] == {"alt": None, "neu": "Feuer unter Kontrolle"}


def test_eingabeart_wird_gespeichert(melder):
    eingabe = {"an": {"art": "text"}, "inhalt": {"art": "sprache", "rohtext": "feuer unter kontrolle", "modell": "large-v3-turbo"}}
    n = melder.post("/api/messages", json=nachricht(eingabe=eingabe)).json()
    assert n["eingabe"]["inhalt"] == {"art": "sprache", "rohtext": "feuer unter kontrolle", "modell": "large-v3-turbo"}


def test_validierung(melder):
    assert melder.post("/api/messages", json=nachricht(inhalt="")).status_code == 422
    assert melder.post("/api/messages", json=nachricht(erfasst_at="2026-11-07T10:00:00")).status_code == 422


def test_elw_bekommt_neue_nachricht_live(melder, elw):
    with elw.websocket_connect("/api/ws/elw") as ws:
        melder.post("/api/messages", json=nachricht(inhalt="Live!"))
        event = ws.receive_json()
    assert event["type"] == "nachricht.neu"
    assert event["nachricht"]["inhalt"] == "Live!"


def test_websocket_nicht_fuer_melder(melder):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), melder.websocket_connect("/api/ws/elw") as ws:
        ws.receive_json()


def test_transcribe_empfaenger_mit_vorschlaegen(melder, stt):
    stt.next_text = "Einsatzabschnitt Wasser"
    r = melder.post("/api/speech/transcribe", data={"field": "an"}, files={"audio": ("a.webm", b"audio", "audio/webm")})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "Einsatzabschnitt Wasser"
    assert body["vorschlaege"][0]["name"] == "EA Wasserversorgung"
    # Funktionen des Einsatzes landen als Vokabular im Prompt
    hint = stt.calls[0][1]
    assert hint.field == "an" and "EA Brand" in hint.prompt


def test_transcribe_inhalt_ohne_vorschlaege(melder, stt):
    stt.next_text = "Feuer aus."
    r = melder.post("/api/speech/transcribe", data={"field": "inhalt"}, files={"audio": ("a.m4a", b"audio", "audio/mp4")})
    assert r.json()["vorschlaege"] == []
    assert "Atemschutz" in stt.calls[0][1].prompt


def test_transcribe_ungueltiges_feld(melder):
    r = melder.post("/api/speech/transcribe", data={"field": "xyz"}, files={"audio": ("a.webm", b"audio")})
    assert r.status_code == 422


def test_keine_caching_header_fuer_api(melder):
    r = melder.get("/api/auth/me")
    assert r.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_session_cookie_flags(app):
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"name": "Melder 1", "rolle": "melder", "funktion": "EA Brand"})
        cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_alte_clients_mit_prioritaet_werden_nicht_abgewiesen(melder):
    r = melder.post("/api/messages", json=nachricht(prioritaet="blitz"))
    assert r.status_code == 201 and "prioritaet" not in r.json()


# --- Status und Beobachter (Phase 4) ---


def test_status_setzen_mit_audit_und_live(melder, elw, beobachter):
    nid = melder.post("/api/messages", json=nachricht()).json()["id"]
    with beobachter.websocket_connect("/api/ws/elw") as ws:
        r = elw.put(f"/api/messages/{nid}/status", json={"status": "gesichtet"})
        event = ws.receive_json()
    assert r.status_code == 200 and r.json()["status"] == "gesichtet"
    assert event["type"] == "nachricht.geaendert"
    assert event["nachricht"]["id"] == nid and event["nachricht"]["status"] == "gesichtet"

    audit = elw.get(f"/api/messages/{nid}/audit").json()
    assert [(a["aktion"], a["funktion"], a["name"]) for a in audit] == [
        ("erstellt", "EA Brand", "Melder 1"),
        ("status", "ELW", "ELW"),
    ]
    assert audit[1]["aenderungen"] == {"status": {"alt": "neu", "neu": "gesichtet"}}


def test_audit_kennt_den_stand_beim_schreiben(melder, elw):
    """Zwei ELW-Plätze gleichzeitig: Platz 1 hat die Nachricht noch als „neu“ gelesen, Platz 2 ist schneller."""
    nid = melder.post("/api/messages", json=nachricht()).json()["id"]
    with new_session() as platz1, new_session() as platz2:
        veraltet = platz1.get(Nachricht, nid)
        anmeldung1 = platz1.scalars(select(Anmeldung).where(Anmeldung.funktion == "ELW")).one()
        anmeldung2 = platz2.scalars(select(Anmeldung).where(Anmeldung.funktion == "ELW")).one()
        message_service.setze_status(platz2, anmeldung2, platz2.get(Nachricht, nid), Status.GESICHTET)
        message_service.setze_status(platz1, anmeldung1, veraltet, Status.ERLEDIGT)
    status = [a["aenderungen"]["status"] for a in elw.get(f"/api/messages/{nid}/audit").json()[1:]]
    assert status == [{"alt": "neu", "neu": "gesichtet"}, {"alt": "gesichtet", "neu": "erledigt"}]


def test_gleicher_status_ohne_audit(melder, elw):
    nid = melder.post("/api/messages", json=nachricht()).json()["id"]
    assert elw.put(f"/api/messages/{nid}/status", json={"status": "neu"}).status_code == 200
    assert len(elw.get(f"/api/messages/{nid}/audit").json()) == 1


def test_status_validierung_und_rechte(melder, elw, beobachter):
    nid = melder.post("/api/messages", json=nachricht()).json()["id"]
    assert elw.put(f"/api/messages/{nid}/status", json={"status": "weitergeleitet"}).status_code == 422
    assert melder.put(f"/api/messages/{nid}/status", json={"status": "erledigt"}).status_code == 403
    assert beobachter.put(f"/api/messages/{nid}/status", json={"status": "erledigt"}).status_code == 403
    assert elw.put("/api/messages/999/status", json={"status": "erledigt"}).status_code == 404
    assert elw.get(f"/api/messages/{nid}").json()["status"] == "neu"


def test_beobachter_liest_alles_und_erfasst_nichts(melder, melder2, beobachter):
    nid = melder.post("/api/messages", json=nachricht(inhalt="von 1")).json()["id"]
    melder2.post("/api/messages", json=nachricht(inhalt="von 2"))
    assert beobachter.get("/api/auth/me").json()["rolle"] == "beobachter"
    assert [n["inhalt"] for n in beobachter.get("/api/messages").json()] == ["von 2", "von 1"]
    assert beobachter.get(f"/api/messages/{nid}").status_code == 200
    assert beobachter.get(f"/api/messages/{nid}/audit").status_code == 200
    assert beobachter.post("/api/messages", json=nachricht()).status_code == 403
    r = beobachter.post("/api/speech/transcribe", data={"field": "inhalt"}, files={"audio": ("a.webm", b"x")})
    assert r.status_code == 403


def test_elw_erfasst_selbst(elw):
    r = elw.post("/api/messages", json=nachricht(an="EA Brand", inhalt="Per Funk: Lage stabil"))
    assert r.status_code == 201 and r.json()["von_funktion"] == "ELW"


def test_beobachter_laedt_keine_fotos_hoch(beobachter):
    r = beobachter.post("/api/uploads/foto", files={"datei": ("f.jpg", b"x", "image/jpeg")})
    assert r.status_code == 403


def test_elw_sieht_in_der_melder_ansicht_nur_eigene(melder, elw):
    melder.post("/api/messages", json=nachricht(inhalt="vom Melder"))
    elw.post("/api/messages", json=nachricht(inhalt="vom ELW"))
    assert [n["inhalt"] for n in elw.get("/api/messages", params={"nur_eigene": True}).json()] == ["vom ELW"]
    assert len(elw.get("/api/messages").json()) == 2


# --- Einsatz öffnen (Phase 5) ---


def test_health_ohne_anmeldung(app):
    with TestClient(app) as c:
        assert c.get("/api/health").json() == {"ok": True, "stt_bereit": True}


def test_einsatz_oeffnen_legt_nur_einmal_an(tmp_path, monkeypatch):
    monkeypatch.setenv("MELDI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MELDI_EINSATZ_KENNUNG", "abc123")
    monkeypatch.setenv("MELDI_EINSATZ_BEZEICHNUNG", "B3 Hauptstraße")
    monkeypatch.setenv("MELDI_ABLAGE_DIR", str(tmp_path / "nas"))
    get_settings.cache_clear()
    try:
        for _ in range(2):  # zweiter Start: derselbe Einsatz wird fortgesetzt
            with TestClient(create_app()) as c:
                r = c.post("/api/auth/login", json={"name": "A", "rolle": "elw", "funktion": "ELW"})
                assert r.json()["einsatz"] == "B3 Hauptstraße"
        assert (tmp_path / "einsaetze" / "abc123" / "meldi.db").is_file()
        assert not (tmp_path / "nas" / "meldi.db").exists()
        with new_session() as db:
            assert db.query(Einsatz).count() == 1
    finally:
        get_settings.cache_clear()
