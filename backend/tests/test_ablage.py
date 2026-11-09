import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import new_session
from app.models import Einsatz
from app.services import ablage, message_service


def nachricht(**kw):
    return {"an": "Einsatzleitung", "inhalt": "Feuer unter Kontrolle", **kw}


def sprich(client, stt, text: str, feld: str = "inhalt", audio: bytes = b"audio") -> str | None:
    stt.next_text = text
    r = client.post("/api/speech/transcribe", data={"field": feld}, files={"audio": ("a.webm", audio, "audio/webm")})
    assert r.status_code == 200, r.text
    return r.json()["aufnahme_id"]


def einsatz_ordner():
    (ordner,) = [p for p in get_settings().ablage_root.iterdir() if p.name != ablage.SENDEN]
    return ordner


def vorlaeufig(anmeldung_id: int = 1):
    d = get_settings().vorlaeufig_dir / str(anmeldung_id)
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def test_nachricht_landet_menschenlesbar_in_der_ablage(melder):
    eingabe = {"inhalt": {"art": "sprache", "rohtext": "feuer", "modell": "m"}}
    melder.post("/api/messages", json=nachricht(eingabe=eingabe))
    ordner = einsatz_ordner()
    assert ordner.name.endswith("_Test-Einsatz_E1")
    assert json.loads((ordner / "einsatz.json").read_text(encoding="utf-8"))["bezeichnung"] == "Test-Einsatz"

    n_ordner = ordner / "0001_EA-Brand"
    txt = (n_ordner / "nachricht.txt").read_text(encoding="utf-8")
    assert "Nachricht Nr. 1" in txt and "EA Brand (Melder 1)" in txt and "Feuer unter Kontrolle" in txt
    assert "Inhalt: feuer" in txt  # Rohtext der Erkennung
    daten = json.loads((n_ordner / "nachricht.json").read_text(encoding="utf-8"))
    assert daten["an"] == "Einsatzleitung" and daten["anhaenge"] == []
    (zeile,) = (n_ordner / "protokoll.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(zeile)["aktion"] == "erstellt"


def test_aufnahmen_werden_mit_pruefsumme_uebernommen(melder, elw, stt):
    an = sprich(melder, stt, "Einsatzleitung", feld="an", audio=b"an-audio")
    i1 = sprich(melder, stt, "Feuer", audio=b"inhalt-1")
    i2 = sprich(melder, stt, "unter Kontrolle", audio=b"inhalt-2")
    n = melder.post("/api/messages", json=nachricht(anhaenge=[an, i1, i2])).json()

    assert [(a["dateiname"], a["feld"]) for a in n["anhaenge"]] == [
        ("an_1.webm", "an"), ("inhalt_1.webm", "inhalt"), ("inhalt_2.webm", "inhalt"),
    ]
    assert n["anhaenge"][1]["meta"]["rohtext"] == "Feuer"
    n_ordner = einsatz_ordner() / "0001_EA-Brand"
    assert (n_ordner / "inhalt_2.webm").read_bytes() == b"inhalt-2"
    daten = json.loads((n_ordner / "nachricht.json").read_text(encoding="utf-8"))
    assert daten["anhaenge"][0]["sha256"] == hashlib.sha256(b"an-audio").hexdigest()
    assert "inhalt_2.webm" in (n_ordner / "nachricht.txt").read_text(encoding="utf-8")

    audit = elw.get(f"/api/messages/{n['id']}/audit").json()
    assert audit[0]["aenderungen"]["anhaenge"]["neu"][0]["datei"] == "an_1.webm"

    url = f"/api/messages/{n['id']}/anhaenge/{n['anhaenge'][0]['id']}"
    r = elw.get(url)
    assert r.status_code == 200 and r.content == b"an-audio"
    assert r.headers["content-type"] == "audio/webm" and r.headers["cache-control"] == "no-store"
    assert melder.get(url).status_code == 403


def test_nicht_gesendete_aufnahmen_werden_geloescht(melder, stt):
    sprich(melder, stt, "Einsatzleitung", feld="an")  # verworfen, neu eingesprochen
    an = sprich(melder, stt, "Einsatzleitung", feld="an")
    assert len(vorlaeufig()) == 4  # je Aufnahme Datei + JSON
    melder.post("/api/messages", json=nachricht(anhaenge=[an]))
    assert vorlaeufig() == []
    assert sorted(p.name for p in (einsatz_ordner() / "0001_EA-Brand").glob("*.webm")) == ["an_1.webm"]


def test_abmelden_loescht_vorlaeufige_aufnahmen(melder, stt):
    sprich(melder, stt, "Feuer")
    assert vorlaeufig()
    melder.post("/api/auth/logout")
    assert vorlaeufig() == []


def test_leere_erkennung_wird_nicht_abgelegt(melder, stt):
    assert sprich(melder, stt, "") is None
    assert vorlaeufig() == []


def test_fremde_oder_fehlende_anhaenge_blockieren_nicht(melder, melder2, elw, stt):
    fremd = sprich(melder2, stt, "Feuer")
    eigen = sprich(melder, stt, "Feuer")
    r = melder.post("/api/messages", json=nachricht(anhaenge=[fremd, "0" * 32, "../../etwas", eigen]))
    assert r.status_code == 201
    n = r.json()
    assert n["fehlende_anhaenge"] == 3
    assert [a["dateiname"] for a in n["anhaenge"]] == ["inhalt_1.webm"]  # nichts Fremdes übernommen
    assert vorlaeufig(2)  # die Aufnahme von Melder 2 bleibt unangetastet
    audit = elw.get(f"/api/messages/{n['id']}/audit").json()
    assert audit[0]["aenderungen"]["fehlende_anhaenge"]["neu"] == 3
    txt = (einsatz_ordner() / "0001_EA-Brand" / "nachricht.txt").read_text(encoding="utf-8")
    assert "3 Anhang/Anhänge kamen nicht an" in txt


def test_nach_serverneustart_kommt_die_nachricht_trotzdem_an(app, melder, stt):
    aufnahme = sprich(melder, stt, "Feuer")
    with TestClient(app):  # Neustart räumt vorläufige Uploads ab
        pass
    r = melder.post("/api/messages", json=nachricht(anhaenge=[aufnahme]))
    assert r.status_code == 201 and r.json()["fehlende_anhaenge"] == 1


def test_wiederholtes_absenden_legt_keine_zweite_nachricht_an(melder, elw, stt):
    aufnahme = sprich(melder, stt, "Feuer")
    body = nachricht(anhaenge=[aufnahme], sende_id="a1b2c3d4e5f6a7b8")
    with elw.websocket_connect("/api/ws/elw") as ws:
        erste = melder.post("/api/messages", json=body)
        assert ws.receive_json()["nachricht"]["lfd_nr"] == 1
        # Antwort ging verloren, das Handy sendet erneut – die Aufnahme ist inzwischen übernommen.
        zweite = melder.post("/api/messages", json=body)
    assert erste.status_code == 201 and zweite.status_code == 200
    assert zweite.json()["id"] == erste.json()["id"]
    assert zweite.json()["anhaenge"][0]["dateiname"] == "inhalt_1.webm"
    assert len(elw.get("/api/messages").json()) == 1
    # Eine neue Sende-ID ist eine neue Nachricht
    assert melder.post("/api/messages", json=nachricht(sende_id="neueid123")).json()["lfd_nr"] == 2


def test_mime_typ_kommt_nie_vom_handy(melder, elw, stt):
    stt.next_text = "Feuer"
    r = melder.post("/api/speech/transcribe", data={"field": "inhalt"},
                    files={"audio": ("a.html", b"<html>", "text/html")})
    n = melder.post("/api/messages", json=nachricht(anhaenge=[r.json()["aufnahme_id"]])).json()
    (a,) = n["anhaenge"]
    assert a["dateiname"] == "inhalt_1.bin" and a["mime"] == "application/octet-stream"
    antwort = elw.get(f"/api/messages/{n['id']}/anhaenge/{a['id']}")
    assert antwort.headers["content-type"] == "application/octet-stream"
    assert antwort.headers["content-disposition"].startswith("attachment")


def test_rest_eines_abgebrochenen_absendens_wird_beiseitegeschoben(melder):
    melder.post("/api/messages", json=nachricht())
    rest = einsatz_ordner() / "0002_EA-Brand"
    rest.mkdir()
    (rest / "foto_1.jpg").write_bytes(b"rest")
    assert melder.post("/api/messages", json=nachricht()).status_code == 201
    assert (rest / "nachricht.txt").is_file()
    (alt,) = einsatz_ordner().glob("0002_EA-Brand_alt_*")
    assert (alt / "foto_1.jpg").read_bytes() == b"rest"


def test_ablageordner_bleibt_fest(melder, elw, stt, db_url):
    from app.db import new_session
    from app.models import Einsatz

    erste = melder.post("/api/messages", json=nachricht(anhaenge=[sprich(melder, stt, "Feuer")])).json()
    with new_session() as db:
        db.get(Einsatz, 1).bezeichnung = "Umbenannt"
        db.commit()
    melder.post("/api/messages", json=nachricht())
    assert einsatz_ordner().name.endswith("_Test-Einsatz_E1")  # weiterhin genau ein Einsatzordner
    assert elw.get(f"/api/messages/{erste['id']}/anhaenge/{erste['anhaenge'][0]['id']}").status_code == 200


def test_fehler_beim_ablegen_hinterlaesst_nichts(app, stt, monkeypatch):
    with TestClient(app, raise_server_exceptions=False) as melder:
        melder.post("/api/auth/login", json={"name": "Melder 1", "rolle": "melder", "funktion": "EA Brand"})
        aufnahme = sprich(melder, stt, "Feuer")

        def kaputt(*a, **kw):
            raise OSError("Datenträger voll")

        monkeypatch.setattr(ablage, "protokolliere", kaputt)
        r = melder.post("/api/messages", json=nachricht(anhaenge=[aufnahme]))
        assert r.status_code == 503 and "Einsatzablage" in r.json()["detail"]
        assert not (einsatz_ordner() / "0001_EA-Brand").exists()
        assert melder.get("/api/messages").json() == []

        monkeypatch.undo()
        r = melder.post("/api/messages", json=nachricht(anhaenge=[aufnahme]))  # erneut senden klappt
        assert r.status_code == 201 and r.json()["anhaenge"][0]["dateiname"] == "inhalt_1.webm"


def test_serverstart_raeumt_vorlaeufige_uploads_auf(app):
    rest = get_settings().vorlaeufig_dir / "7"
    rest.mkdir(parents=True)
    (rest / "x.webm").write_bytes(b"x")
    with TestClient(app):
        pass
    assert not rest.exists()


def test_serverstart_scheitert_bei_nicht_beschreibbarer_ablage(app, tmp_path, monkeypatch):
    (tmp_path / "datei").write_bytes(b"")
    monkeypatch.setattr(ablage, "wurzel", lambda: tmp_path / "datei" / "ablage")
    with pytest.raises(OSError), TestClient(app):
        pass


def _kurz_gesperrt(echt, mal: int = 2):
    fehler = iter([PermissionError(13, "gesperrt")] * mal)

    def gesperrt(*a, **kw):
        if f := next(fehler, None):
            raise f
        return echt(*a, **kw)

    return gesperrt


def test_absenden_wartet_kurze_dateisperre_ab(melder, monkeypatch):
    """Unter Windows hält der Virenscanner frisch geschriebene Dateien oft kurz offen."""
    monkeypatch.setattr(ablage.time, "sleep", lambda _: None)
    monkeypatch.setattr(Path, "rename", _kurz_gesperrt(Path.rename))
    assert melder.post("/api/messages", json=nachricht()).status_code == 201
    assert (einsatz_ordner() / "0001_EA-Brand" / "nachricht.txt").is_file()


def test_status_wartet_kurze_dateisperre_ab(melder, elw, monkeypatch):
    nid = melder.post("/api/messages", json=nachricht()).json()["id"]
    monkeypatch.setattr(ablage.time, "sleep", lambda _: None)
    monkeypatch.setattr(ablage.os, "replace", _kurz_gesperrt(os.replace))
    assert elw.put(f"/api/messages/{nid}/status", json={"status": "erledigt"}).status_code == 200
    n_ordner = einsatz_ordner() / "0001_EA-Brand"
    assert json.loads((n_ordner / "nachricht.json").read_text(encoding="utf-8"))["status"] == "erledigt"


def test_dauerhafte_dateisperre_meldet_verstaendlichen_fehler(melder, elw, monkeypatch):
    nid = melder.post("/api/messages", json=nachricht()).json()["id"]
    monkeypatch.setattr(ablage.time, "sleep", lambda _: None)
    monkeypatch.setattr(ablage.os, "replace", _kurz_gesperrt(os.replace, mal=99))
    r = elw.put(f"/api/messages/{nid}/status", json={"status": "erledigt"})
    assert r.status_code == 503 and "Einsatzablage" in r.json()["detail"]
    monkeypatch.undo()
    assert elw.get(f"/api/messages/{nid}").json()["status"] == "neu"


def test_ordnername_ist_windows_tauglich():
    assert ablage.ordnername('EA "Brand": Nord/Süd?') == "EA-Brand-NordSüd"
    assert ablage.ordnername("...") == "ohne-Namen"


def test_status_landet_in_der_ablage(melder, elw):
    nid = melder.post("/api/messages", json=nachricht()).json()["id"]
    elw.put(f"/api/messages/{nid}/status", json={"status": "erledigt"})
    n_ordner = einsatz_ordner() / "0001_EA-Brand"
    assert json.loads((n_ordner / "nachricht.json").read_text(encoding="utf-8"))["status"] == "erledigt"
    zeilen = [json.loads(z) for z in (n_ordner / "protokoll.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [z["aktion"] for z in zeilen] == ["erstellt", "status"]
    assert zeilen[1]["name"] == "ELW" and zeilen[1]["aenderungen"]["status"] == {"alt": "neu", "neu": "erledigt"}


def test_status_antwort_behaelt_anhaenge(melder, elw, stt):
    aufnahme = sprich(melder, stt, "Feuer")
    nid = melder.post("/api/messages", json=nachricht(anhaenge=[aufnahme])).json()["id"]
    for status in ("erledigt", "erledigt"):  # beim zweiten Mal ohne Änderung
        r = elw.put(f"/api/messages/{nid}/status", json={"status": status}).json()
        assert r["status"] == "erledigt" and len(r["anhaenge"]) == 1 and r["von_name"] == "Melder 1"


def test_status_behaelt_hinweis_auf_fehlende_anhaenge(melder, elw):
    nid = melder.post("/api/messages", json=nachricht(anhaenge=["0" * 32])).json()["id"]
    elw.put(f"/api/messages/{nid}/status", json={"status": "gesichtet"})
    n_ordner = einsatz_ordner() / "0001_EA-Brand"
    assert json.loads((n_ordner / "nachricht.json").read_text(encoding="utf-8"))["fehlende_anhaenge"] == 1
    assert "1 Anhang/Anhänge kamen nicht an" in (n_ordner / "nachricht.txt").read_text(encoding="utf-8")


def test_status_fehler_beim_ablegen_bleibt_konsistent(app, melder, monkeypatch):
    nid = melder.post("/api/messages", json=nachricht()).json()["id"]
    with TestClient(app, raise_server_exceptions=False) as elw:
        elw.post("/api/auth/login", json={"name": "ELW", "rolle": "elw", "funktion": "ELW"})

        def kaputt(*a, **kw):
            raise OSError("Datenträger voll")

        monkeypatch.setattr(ablage, "protokolliere", kaputt)
        assert elw.put(f"/api/messages/{nid}/status", json={"status": "erledigt"}).status_code == 503
        monkeypatch.undo()
        assert elw.get(f"/api/messages/{nid}").json()["status"] == "neu"
        assert len(elw.get(f"/api/messages/{nid}/audit").json()) == 1
    n_ordner = einsatz_ordner() / "0001_EA-Brand"
    assert json.loads((n_ordner / "nachricht.json").read_text(encoding="utf-8"))["status"] == "neu"


# --- Einsatz öffnen und Neuaufbau (Phase 5) ---


def test_vorlaeufige_uploads_liegen_nicht_in_der_ablage(melder, stt):
    sprich(melder, stt, "Feuer")
    assert list(get_settings().vorlaeufig_dir.rglob("*.json"))
    assert not list(get_settings().ablage_root.rglob("*.json"))


def test_neuaufbau_nach_geloeschtem_ordner(melder, elw, stt, monkeypatch, tmp_path):
    aufnahme = sprich(melder, stt, "Feuer")
    nid = melder.post("/api/messages", json=nachricht(anhaenge=[aufnahme])).json()["id"]
    assert elw.put(f"/api/messages/{nid}/status", json={"status": "gesichtet"}).status_code == 200

    # Neuer Ordner: wie „In neuem Ordner fortsetzen“ im Startfenster
    monkeypatch.setenv("MELDI_ABLAGE_DIR", str(tmp_path / "neu"))
    get_settings.cache_clear()
    with new_session() as db:
        einsatz = db.get(Einsatz, 1)
        assert message_service.ablage_neu_aufbauen(db, einsatz) == 1
        assert message_service.ablage_neu_aufbauen(db, einsatz) == 0  # wiederholbar

    n_ordner = get_settings().ablage_root / einsatz.ablage_ordner / "0001_EA-Brand"
    daten = json.loads((n_ordner / "nachricht.json").read_text(encoding="utf-8"))
    assert daten["status"] == "gesichtet" and len(daten["fehlende_dateien"]) == 1
    assert "fehlen im Ordner" in (n_ordner / "nachricht.txt").read_text(encoding="utf-8")
    zeilen = [json.loads(z) for z in (n_ordner / "protokoll.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [z["aktion"] for z in zeilen] == ["erstellt", "status", "ablage_neu_aufgebaut"]

    # Nummerierung läuft weiter, Status lässt sich weiter setzen
    assert melder.post("/api/messages", json=nachricht()).json()["lfd_nr"] == 2
    assert elw.put(f"/api/messages/{nid}/status", json={"status": "erledigt"}).status_code == 200
    daten = json.loads((n_ordner / "nachricht.json").read_text(encoding="utf-8"))
    assert daten["status"] == "erledigt" and len(daten["fehlende_dateien"]) == 1
