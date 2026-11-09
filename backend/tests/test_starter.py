import json
import re
import signal
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import PROJECT_DIR
from app.starter import ordner as o
from app.starter import prozesse as p
from app.starter.ordner import OrdnerArt, Startauftrag

KENNUNG = "a" * 32


def _lege_db_an(data_dir: Path, kennung: str, bezeichnung="Brand", naechste=8, ende=None, wal=True) -> Path:
    db = o.einsatz_db(data_dir, kennung)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE einsatz (id INTEGER PRIMARY KEY, bezeichnung, beginn, ende, naechste_lfd_nr)")
    con.execute("INSERT INTO einsatz (bezeichnung, beginn, ende, naechste_lfd_nr) VALUES (?, ?, ?, ?)",
                (bezeichnung, "2026-11-07 14:32:00.000000", ende, naechste))
    con.commit()
    con.close()
    return db


def _einsatzordner(tmp_path: Path, kennung=KENNUNG, bezeichnung="Brand") -> Path:
    ordner = tmp_path / "nas" / "einsatz"
    ordner.mkdir(parents=True)
    o.schreibe_kennung(ordner, kennung, bezeichnung, datetime(2026, 11, 7, 14, 32, tzinfo=UTC))
    return ordner


# --- Ordner erkennen ---------------------------------------------------------------------------------------


def test_analyse_nicht_existierend_ist_neu(tmp_path):
    assert o.analysiere(tmp_path, tmp_path / "gibtsnicht").art == OrdnerArt.NEU


def test_analyse_leer_ist_neu(tmp_path):
    ordner = tmp_path / "leer"
    ordner.mkdir()
    assert o.analysiere(tmp_path, ordner).art == OrdnerArt.NEU


def test_analyse_fremder_ordner(tmp_path):
    ordner = tmp_path / "fremd"
    ordner.mkdir()
    (ordner / "urlaub.jpg").write_bytes(b"x")
    a = o.analysiere(tmp_path, ordner)
    assert a.art == OrdnerArt.FREMD
    assert o.vorschlag(a, None).rueckfrage


def test_analyse_datei_statt_ordner(tmp_path):
    datei = tmp_path / "datei"
    datei.write_bytes(b"x")
    assert o.analysiere(tmp_path, datei).art == OrdnerArt.UNBRAUCHBAR


def test_analyse_vorhanden_liest_db(tmp_path):
    ordner = _einsatzordner(tmp_path, bezeichnung="Name aus Kennung")
    _lege_db_an(tmp_path, KENNUNG, bezeichnung="Name aus DB", naechste=8)
    a = o.analysiere(tmp_path, ordner)
    assert a.art == OrdnerArt.VORHANDEN
    assert (a.einsatz.bezeichnung, a.einsatz.nachrichten) == ("Name aus DB", 7)
    assert a.einsatz.beginn == datetime(2026, 11, 7, 14, 32, tzinfo=UTC)
    v = o.vorschlag(a, None)
    assert v.knopf == "Einsatz fortsetzen" and v.name_gesperrt and v.erlaubt


def test_analyse_liest_db_waehrend_server_sie_offen_haelt(tmp_path):
    ordner = _einsatzordner(tmp_path)
    db = _lege_db_an(tmp_path, KENNUNG, naechste=3)
    offen = sqlite3.connect(db)
    offen.execute("UPDATE einsatz SET naechste_lfd_nr = 5")
    offen.commit()
    try:
        assert o.analysiere(tmp_path, ordner).einsatz.nachrichten == 4
    finally:
        offen.close()


def test_analyse_db_ohne_schema_nutzt_kennung(tmp_path):
    ordner = _einsatzordner(tmp_path, bezeichnung="Aus Kennung")
    db = o.einsatz_db(tmp_path, KENNUNG)
    db.parent.mkdir(parents=True)
    sqlite3.connect(db).close()
    db.write_bytes(b"")
    a = o.analysiere(tmp_path, ordner)
    assert a.art == OrdnerArt.VORHANDEN
    assert (a.einsatz.bezeichnung, a.einsatz.nachrichten) == ("Aus Kennung", 0)


def test_analyse_db_fehlt_bei_vorhandenen_nachrichten(tmp_path):
    ordner = _einsatzordner(tmp_path)
    (ordner / "2026-11-07_1432_Brand_E1").mkdir()
    a = o.analysiere(tmp_path, ordner)
    assert a.art == OrdnerArt.DB_FEHLT
    assert not o.vorschlag(a, None).erlaubt
    with pytest.raises(ValueError):
        o.vorbereiten(tmp_path, a, None, "egal")


def test_analyse_nur_kennung_ohne_db_ist_fortsetzbar(tmp_path):
    """Start abgebrochen, bevor der Server die Datenbank anlegen konnte."""
    assert o.analysiere(tmp_path, _einsatzordner(tmp_path)).art == OrdnerArt.VORHANDEN


@pytest.mark.parametrize("inhalt", [
    "kein json", "[]", '{"kennung": "abc", "bezeichnung": "x"}',
    json.dumps({"kennung": "../../boese", "bezeichnung": "x"}),
])
def test_beschaedigte_kennung_ist_nicht_neu(tmp_path, inhalt):
    ordner = tmp_path / "x"
    ordner.mkdir()
    (ordner / o.KENNUNGSDATEI).write_text(inhalt, encoding="utf-8")
    a = o.analysiere(tmp_path, ordner)
    assert a.art == OrdnerArt.UNBRAUCHBAR
    assert not o.vorschlag(a, None).erlaubt


# --- Vorbereiten -------------------------------------------------------------------------------------------


def test_neuer_einsatz_schreibt_kennung_und_merkt_ordner(tmp_path):
    ordner = tmp_path / "nas" / "neu"
    auftrag = o.neuer_einsatz(tmp_path, ordner, "  B3 Hauptstr. 5 ")
    assert auftrag.bezeichnung == "B3 Hauptstr. 5" and not auftrag.neu_aufbauen
    assert len(auftrag.kennung) == 32
    k = o.lies_kennung(ordner)
    assert (k.kennung, k.bezeichnung) == (auftrag.kennung, auftrag.bezeichnung)
    assert k.beginn.tzinfo is not None
    assert [e.name for e in ordner.iterdir()] == [o.KENNUNGSDATEI]  # keine Reste
    bekannt = o.bekannte_einsaetze(tmp_path)
    assert [(e.kennung, e.ordner, e.ordner_fehlt) for e in bekannt] == [(auftrag.kennung, ordner, False)]


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_neuer_einsatz_prueft_namen(tmp_path, name):
    with pytest.raises(ValueError):
        o.neuer_einsatz(tmp_path, tmp_path / "n", name)
    assert not (tmp_path / "n").exists()


def test_fortsetzen_behaelt_kennung(tmp_path):
    ordner = _einsatzordner(tmp_path)
    _lege_db_an(tmp_path, KENNUNG)
    auftrag = o.vorbereiten(tmp_path, o.analysiere(tmp_path, ordner), None, "wird ignoriert")
    assert (auftrag.kennung, auftrag.bezeichnung, auftrag.neu_aufbauen) == (KENNUNG, "Brand", False)
    assert o.lies_kennung(ordner).kennung == KENNUNG


def test_bekannte_einsaetze_erkennt_fehlenden_ordner_und_sortiert(tmp_path):
    alt = o.neuer_einsatz(tmp_path, tmp_path / "alt", "Alt")
    time.sleep(0.01)
    neu = o.neuer_einsatz(tmp_path, tmp_path / "neu", "Neu")
    (tmp_path / "alt" / o.KENNUNGSDATEI).unlink()
    (tmp_path / "alt").rmdir()
    bekannt = o.bekannte_einsaetze(tmp_path)
    assert [e.kennung for e in bekannt] == [neu.kennung, alt.kennung]
    assert [e.ordner_fehlt for e in bekannt] == [False, True]


def test_bekannte_einsaetze_ohne_verzeichnis(tmp_path):
    assert o.bekannte_einsaetze(tmp_path) == []


def test_bekannte_einsaetze_ignoriert_fremde_verzeichnisse(tmp_path):
    (tmp_path / "einsaetze" / "kein-einsatz").mkdir(parents=True)
    (tmp_path / "einsaetze" / KENNUNG).mkdir()
    assert o.bekannte_einsaetze(tmp_path) == []


def test_in_neuem_ordner_fortsetzen(tmp_path):
    _lege_db_an(tmp_path, KENNUNG, naechste=8)
    o.merke_einsatz(tmp_path, KENNUNG, tmp_path / "weg", "Brand", None)
    umzug = o.bekannte_einsaetze(tmp_path)[0]
    assert umzug.ordner_fehlt and umzug.nachrichten == 7

    a = o.analysiere(tmp_path, tmp_path / "ersatz")
    v = o.vorschlag(a, umzug)
    assert (v.knopf, v.erlaubt, v.name_gesperrt, v.bezeichnung) == ("In neuem Ordner fortsetzen", True, True, "Brand")
    auftrag = o.vorbereiten(tmp_path, a, umzug, "egal")
    assert auftrag.neu_aufbauen and auftrag.kennung == KENNUNG
    assert o.kennung_vorhanden(tmp_path / "ersatz", KENNUNG)
    assert o.bekannte_einsaetze(tmp_path)[0].ordner == tmp_path / "ersatz"


def test_umzug_in_ordner_eines_anderen_einsatzes_verboten(tmp_path):
    ordner = _einsatzordner(tmp_path, kennung="b" * 32)
    (ordner / "0001").mkdir()
    umzug = o.EinsatzInfo(KENNUNG, "Brand")
    a = o.analysiere(tmp_path, ordner)
    assert not o.vorschlag(a, umzug).erlaubt
    with pytest.raises(ValueError):
        o.vorbereiten(tmp_path, a, umzug, "egal")
    with pytest.raises(ValueError):
        o.in_neuem_ordner_fortsetzen(tmp_path, umzug, ordner)


def test_umzug_ordner_wieder_da_wird_normal_fortgesetzt(tmp_path):
    ordner = _einsatzordner(tmp_path)
    _lege_db_an(tmp_path, KENNUNG)
    a = o.analysiere(tmp_path, ordner)
    umzug = o.EinsatzInfo(KENNUNG, "Brand")
    assert o.vorschlag(a, umzug).knopf == "Einsatz fortsetzen"
    assert not o.vorbereiten(tmp_path, a, umzug, "egal").neu_aufbauen


def test_kennung_vorhanden_falscher_einsatz_und_geloescht(tmp_path):
    ordner = _einsatzordner(tmp_path)
    assert o.kennung_vorhanden(ordner, KENNUNG)
    assert not o.kennung_vorhanden(ordner, "b" * 32)
    (ordner / o.KENNUNGSDATEI).unlink()
    assert not o.kennung_vorhanden(ordner, KENNUNG)


def test_pruefe_beschreibbar_legt_an_und_hinterlaesst_nichts(tmp_path):
    ordner = tmp_path / "a" / "b"
    o.pruefe_beschreibbar(ordner)
    assert list(ordner.iterdir()) == []


def test_pruefe_beschreibbar_scheitert_an_datei(tmp_path):
    (tmp_path / "datei").write_bytes(b"")
    with pytest.raises(OSError):
        o.pruefe_beschreibbar(tmp_path / "datei" / "unter")


# --- Prozesse ----------------------------------------------------------------------------------------------


def _befehl(tmp_path: Path, code: str, name="server") -> p.Befehl:
    skript = tmp_path / f"{name}.py"
    skript.write_text(textwrap.dedent(code), encoding="utf-8")
    return p.Befehl(name, [sys.executable, "-u", str(skript)], {}, tmp_path)


LAEUFT = "import time\nprint('gestartet', flush=True)\ntime.sleep(60)\n"
STIRBT = "import sys\nprint('kaputt', flush=True)\nsys.exit(3)\n"


def _warte_bis(bedingung, frist=5.0) -> None:
    ende = time.monotonic() + frist
    while not bedingung():
        assert time.monotonic() < ende, "Bedingung nicht rechtzeitig erfüllt"
        time.sleep(0.02)


def test_kind_starten_loggen_stoppen(tmp_path):
    kind = p.Kind(_befehl(tmp_path, LAEUFT), tmp_path / "logs")
    assert not kind.laeuft and kind.exitcode is None
    kind.starte()
    try:
        assert kind.laeuft
        _warte_bis(lambda: b"gestartet" in kind.logdatei.read_bytes())
    finally:
        kind.stoppe(5)
    assert not kind.laeuft and kind.exitcode is not None
    assert b"--- Start" in kind.logdatei.read_bytes()


def test_kind_absturz_wird_erkannt(tmp_path):
    kind = p.Kind(_befehl(tmp_path, STIRBT), tmp_path / "logs")
    kind.starte()
    _warte_bis(lambda: not kind.laeuft)
    assert kind.exitcode == 3
    kind.stoppe(1)  # bereits beendet: kein Fehler


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM lässt sich unter Windows nicht ignorieren")
def test_kind_ignoriert_terminate_wird_gekillt(tmp_path):
    code = f"""
    import signal, time
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print('bereit', flush=True)
    time.sleep(60)
    """
    kind = p.Kind(_befehl(tmp_path, code), tmp_path / "logs")
    kind.starte()
    _warte_bis(lambda: b"bereit" in kind.logdatei.read_bytes())
    kind.stoppe(0.3)
    assert kind.exitcode == -signal.SIGKILL


def test_kind_log_wird_angehaengt(tmp_path):
    kind = p.Kind(_befehl(tmp_path, STIRBT), tmp_path / "logs")
    for _ in range(2):
        kind.starte()
        _warte_bis(lambda: not kind.laeuft)
    assert kind.logdatei.read_bytes().count(b"--- Start") == 2


def test_dienste_ohne_caddy_laufen_mit_hinweis(tmp_path):
    d = p.Dienste(_befehl(tmp_path, LAEUFT), None, tmp_path / "logs", "192.168.8.10")
    d.starten()
    try:
        assert d.server.laeuft and not d.abgestuerzt
        assert d.caddy_fehler and d.adresse == "http://localhost:8000/"
    finally:
        d.stoppen(5)


def test_adresse_folgt_dem_zustand_von_caddy(tmp_path):
    server = _befehl(tmp_path, LAEUFT)
    caddy = p.Befehl("caddy", server.kommando, server.umgebung, server.cwd)
    d = p.Dienste(server, caddy, tmp_path / "logs", "192.168.8.10")
    d.starten()
    try:
        assert d.adresse == "https://192.168.8.10/"
        d.caddy.stoppe(5)
        assert d.adresse == "http://localhost:8000/"
    finally:
        d.stoppen(5)


def test_dienste_caddy_nicht_startbar_server_laeuft_weiter(tmp_path):
    kaputt = p.Befehl("caddy", [str(tmp_path / "gibtsnicht")], {}, tmp_path)
    d = p.Dienste(_befehl(tmp_path, LAEUFT), kaputt, tmp_path / "logs")
    d.starten()
    try:
        assert d.server.laeuft and d.caddy_fehler
    finally:
        d.stoppen(5)


def test_dienste_neu_starten_nur_abgestuerzte(tmp_path):
    marke = tmp_path / "marke"
    # Erster Lauf stirbt, zweiter bleibt am Leben.
    code = f"""
    import pathlib, sys, time
    marke = pathlib.Path({str(marke)!r})
    if not marke.exists():
        marke.write_text('1')
        sys.exit(1)
    time.sleep(60)
    """
    caddy = _befehl(tmp_path, LAEUFT, name="caddy")
    d = p.Dienste(_befehl(tmp_path, code), caddy, tmp_path / "logs")
    d.starten()
    try:
        _warte_bis(lambda: not d.server.laeuft)
        assert d.abgestuerzt and d.caddy.laeuft
        vorher = d.caddy._prozess.pid
        d.neu_starten()
        assert d.server.laeuft and not d.abgestuerzt
        assert d.caddy._prozess.pid == vorher
    finally:
        d.stoppen(5)
    assert not d.server.laeuft and not d.caddy.laeuft


def test_starter_sperre_verhindert_zweiten_start(tmp_path):
    erste, zweite = p.StarterSperre(tmp_path), p.StarterSperre(tmp_path)
    assert erste.erwerben()
    assert not zweite.erwerben()
    erste.freigeben()
    assert zweite.erwerben()
    zweite.freigeben()


def test_starter_sperre_endet_mit_dem_prozess(tmp_path):
    code = f"""
    import pathlib, sys, time
    from app.starter.prozesse import StarterSperre
    sperre = StarterSperre(pathlib.Path({str(tmp_path)!r}))
    assert sperre.erwerben()
    print('gesperrt', flush=True)
    time.sleep(60)
    """
    kind = subprocess.Popen([sys.executable, "-c", textwrap.dedent(code)], stdout=subprocess.PIPE)
    try:
        assert kind.stdout.readline().strip() == b"gesperrt"
        assert not p.StarterSperre(tmp_path).erwerben()
    finally:
        kind.kill()
        kind.wait()
        kind.stdout.close()
    sperre = p.StarterSperre(tmp_path)
    assert sperre.erwerben()
    sperre.freigeben()


def test_server_umgebung(tmp_path):
    auftrag = Startauftrag(KENNUNG, "Brand", tmp_path / "nas")
    u = p.server_umgebung(tmp_path, auftrag, {"PATH": "x", "MELDI_ABLAGE_NEU_AUFBAUEN": "true"})
    assert u["PATH"] == "x"
    assert u["MELDI_EINSATZ_KENNUNG"] == KENNUNG
    assert u["MELDI_EINSATZ_BEZEICHNUNG"] == "Brand"
    assert u["MELDI_ABLAGE_DIR"] == str(tmp_path / "nas")
    assert u["MELDI_STT_MODEL_DIR"] == str(tmp_path / "models")
    assert u["MELDI_STT_LOCAL_FILES_ONLY"] == "true"
    assert u["HF_HUB_OFFLINE"] == "1" and u["HF_HUB_DISABLE_TELEMETRY"] == "1"
    assert "MELDI_ABLAGE_NEU_AUFBAUEN" not in u  # veralteter Wert aus der Umgebung darf nichts neu aufbauen


def test_server_umgebung_neu_aufbauen(tmp_path):
    auftrag = Startauftrag(KENNUNG, "Brand", tmp_path, neu_aufbauen=True)
    assert p.server_umgebung(tmp_path, auftrag, {})["MELDI_ABLAGE_NEU_AUFBAUEN"] == "true"


def test_server_kommando(monkeypatch):
    monkeypatch.setattr(sys, "executable", "/venv/Scripts/pythonw.exe")
    kommando = p.server_kommando()
    assert Path(kommando[0]).name == "python.exe"
    assert kommando[1:] == ["-m", "uvicorn", "--factory", "app.main:create_app", "--host", "127.0.0.1", "--port", "8000"]


def test_meldi_host_aus_umgebung():
    assert p.meldi_host({"MELDI_HOST": " 10.0.0.5 "}) == "10.0.0.5"


def test_meldi_host_ueberspringt_loopback(monkeypatch):
    monkeypatch.setattr(p.socket, "gethostbyname_ex", lambda _: ("h", [], ["127.0.1.1", "169.254.1.2", "192.168.8.10"]))
    assert p.meldi_host({}) == "192.168.8.10"


def test_meldi_host_ohne_adresse(monkeypatch):
    def fehler(_):
        raise OSError

    monkeypatch.setattr(p.socket, "gethostbyname_ex", fehler)
    assert p.meldi_host({}) == "localhost"


def test_health(tmp_path):
    class Antwort(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true, "stt_bereit": false}')

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Antwort)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert p.health(f"http://127.0.0.1:{server.server_port}/api/health") == {"ok": True, "stt_bereit": False}
    finally:
        server.shutdown()
        server.server_close()


def test_health_nicht_erreichbar():
    assert p.health("http://127.0.0.1:9/api/health", timeout=0.2) is None


def test_starter_laedt_weder_fastapi_noch_datenbank():
    code = (
        "import sys, app.starter.ordner, app.starter.prozesse, app.starter;"
        "boese = [m for m in sys.modules if m.split('.')[0] in ('fastapi', 'sqlalchemy')"
        " or m in ('app.db', 'app.models', 'tkinter')];"
        "print(boese); sys.exit(1 if boese else 0)"
    )
    ergebnis = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr


def test_farben_entsprechen_der_website():
    farben = pytest.importorskip("app.starter.farben")
    css = (PROJECT_DIR / "frontend" / "src" / "shared" / "style.css").read_text(encoding="utf-8")
    hell, dunkel = css.split("@media (prefers-color-scheme: dark)")
    paare = {
        "bg": farben.BG, "surface": farben.SURFACE, "text": farben.TEXT, "muted": farben.MUTED,
        "border": farben.BORDER, "accent": farben.ACCENT, "on-accent": farben.ON_ACCENT, "danger": farben.DANGER,
    }
    for name, paar in paare.items():
        muster = rf"--{name}:\s*(#[0-9a-fA-F]+)"
        assert (re.search(muster, hell).group(1), re.search(muster, dunkel).group(1)) == paar, name


def test_betriebsansicht_zeigt_adresse_datenpfad_und_schrift(tmp_path, monkeypatch):
    """Tk hält selbst keine Referenz auf Textvariablen: Eine nur lokal gehaltene StringVar lässt das Feld leer."""
    tk = pytest.importorskip("tkinter")
    ctk = pytest.importorskip("customtkinter")

    from app.starter import farben
    from app.starter.fenster import Fenster

    farben.anwenden()
    try:
        root = ctk.CTk()
    except tk.TclError:
        pytest.skip("kein Display")
    root.withdraw()
    try:
        ansicht = Fenster(root, tmp_path)
        ablage = tmp_path / "ablage"
        ansicht.auftrag = Startauftrag(KENNUNG, "Brand", ablage)
        ansicht.dienste = SimpleNamespace(
            server=SimpleNamespace(laeuft=False, exitcode=1, logdatei="server.log"),
            caddy=None,
            caddy_fehler=None,
            abgestuerzt=False,
            adresse="https://192.168.8.10/",
        )
        ansicht.zeige_betrieb()
        ansicht._wird_beendet = True  # keine weiteren Takte

        kinder = ansicht.rahmen.winfo_children()
        felder = [kind.get() for kind in kinder if isinstance(kind, ctk.CTkEntry)]
        assert felder[:2] == ["https://192.168.8.10/", str(ablage)]
        assert kinder[0].cget("font").cget("family") == ctk.ThemeManager.theme["CTkFont"]["family"]

        geoeffnet: list[str] = []
        monkeypatch.setattr("webbrowser.open", lambda url: geoeffnet.append(url) or True)
        next(kind for kind in kinder if isinstance(kind, ctk.CTkButton)).invoke()
        assert geoeffnet == ["https://192.168.8.10/"]
    finally:
        root.destroy()
