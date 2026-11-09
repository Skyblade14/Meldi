import pytest
from playwright.sync_api import expect

from app.db import new_session
from app.models import Anmeldung, Rolle
from app.schemas.message import NachrichtCreate
from app.services import message_service
from tests.ui.conftest import (
    ApiMelder,
    anmelden,
    beende_sitzungen,
    erzeuge_nachrichten,
    filter_auswahl,
    jpeg,
    sende_text,
    spreche,
)

pytestmark = pytest.mark.ui

LOGIN = "ELW – Anmeldung"


def zeilen(page):
    return page.get_by_test_id("nachricht-zeile")


def status_setzen(page, status: str) -> None:
    page.get_by_role("group", name="Status setzen").get_by_role("button", name=status, exact=True).click()


def test_neue_nachricht_ohne_reload_mit_zaehler_und_titel(elw_seite, api_melder):
    expect(elw_seite.get_by_text("Noch keine Nachrichten.")).to_be_visible()
    api_melder.sende("Erste")
    api_melder.sende("Zweite")
    expect(zeilen(elw_seite)).to_have_count(2)
    expect(zeilen(elw_seite).first).to_contain_text("Zweite")  # neueste oben
    expect(elw_seite.get_by_role("heading", name="Eingang")).to_contain_text("(2, 2 neu)")
    expect(elw_seite).to_have_title("(2) Meldi – ELW")
    expect(zeilen(elw_seite).first).to_have_class("neu")

    zeilen(elw_seite).first.click()
    expect(elw_seite.get_by_role("heading", name="Eingang")).to_contain_text("(2, 1 neu)")
    expect(elw_seite).to_have_title("(1) Meldi – ELW")
    zeilen(elw_seite).nth(1).click()
    expect(elw_seite.get_by_role("heading", name="Eingang")).to_contain_text("(2)")
    expect(elw_seite).to_have_title("Meldi – ELW")


def test_tastatur_oeffnet_die_nachricht(elw_seite, api_melder):
    api_melder.sende("Per Tastatur")
    zeilen(elw_seite).first.focus()
    elw_seite.keyboard.press("Enter")
    expect(elw_seite.get_by_role("heading", name="Nachricht Nr. 1")).to_be_visible()


def test_status_live_mit_protokoll(elw_seite, desktop, beobachter_seite, api_melder):
    api_melder.sende("Status bitte")
    elw2 = desktop()
    anmelden(elw2, "elw", "Zweiter Platz")
    zeilen(elw2).first.click()
    expect(beobachter_seite.get_by_test_id("status")).to_have_text("neu")

    zeilen(elw_seite).first.click()
    status_setzen(elw_seite, "gesichtet")

    expect(zeilen(elw2).first.get_by_test_id("status")).to_have_text("gesichtet")
    expect(elw2.get_by_test_id("detail-status")).to_have_text("gesichtet")
    expect(beobachter_seite.get_by_test_id("status")).to_have_text("gesichtet")
    expect(elw2.locator(".audit li").nth(1)).to_contain_text("neu → gesichtet durch ELW (Erika ELW)")
    expect(elw_seite.locator(".audit li").first).to_contain_text("erstellt durch EA Wasserversorgung (Api Melder)")


def test_status_fehler_wird_angezeigt(elw_seite, api_melder, waechter):
    waechter.erlaube("ERR_FAILED")
    api_melder.sende("Status bitte")
    zeilen(elw_seite).first.click()
    elw_seite.route("**/status", lambda r: r.abort(), times=1)
    status_setzen(elw_seite, "erledigt")
    expect(elw_seite.get_by_text("Keine Verbindung zum ELW")).to_be_visible()
    expect(elw_seite.get_by_test_id("detail-status")).to_have_text("neu")


def test_auswahl_bleibt_bei_live_updates(elw_seite, api_melder):
    api_melder.sende("Erste")
    zeilen(elw_seite).first.click()
    expect(elw_seite.get_by_role("heading", name="Nachricht Nr. 1")).to_be_visible()
    api_melder.sende("Zweite")
    expect(zeilen(elw_seite)).to_have_count(2)
    expect(elw_seite.get_by_role("heading", name="Nachricht Nr. 1")).to_be_visible()


def test_text_markieren_wechselt_die_nachricht_nicht(elw_seite, api_melder):
    api_melder.sende("Dieser Text wird mit der Maus markiert")
    zelle = zeilen(elw_seite).first.locator("td.inhalt")
    expect(zelle).to_be_visible()
    box = zelle.bounding_box()
    y = box["y"] + box["height"] / 2
    elw_seite.mouse.move(box["x"] + 12, y)
    elw_seite.mouse.down()
    elw_seite.mouse.move(box["x"] + 150, y, steps=5)
    elw_seite.mouse.up()
    assert elw_seite.evaluate("window.getSelection().toString()") != ""
    expect(elw_seite.get_by_role("heading", name="Nachricht Nr. 1")).to_have_count(0)


def test_klick_markiert_ein_feld_im_detail(elw_seite, api_melder):
    api_melder.sende("Zum Kopieren")
    zeilen(elw_seite).first.click()
    elw_seite.locator(".inhalt-voll").click()
    assert elw_seite.evaluate("window.getSelection().toString()") == "Zum Kopieren"


def test_audio_und_foto_laden_trotz_csp(elw_seite, melder_seite, stt, tmp_path):
    stt.antworten = ["Mit Anhang."]
    melder_seite.get_by_label("An", exact=True).fill("ELW")
    spreche(melder_seite, "Inhalt sprechen")
    expect(melder_seite.get_by_label("Inhalt", exact=True)).to_have_value("Mit Anhang.")
    melder_seite.set_input_files("input[type=file]", jpeg(tmp_path / "a.jpg", gps=True))
    expect(melder_seite.locator(".fotos .status")).to_have_count(0)
    melder_seite.get_by_role("button", name="Absenden").click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")

    zeilen(elw_seite).first.click()
    expect(zeilen(elw_seite).first).to_contain_text("📷 1")
    bild = elw_seite.locator(".fotos img")
    expect(bild).to_be_visible()
    elw_seite.wait_for_function("() => document.querySelector('.fotos img').naturalWidth > 0")
    expect(elw_seite.get_by_text("GPS 52.520000, 13.405000")).to_be_visible()
    elw_seite.locator("audio").evaluate("a => a.load()")
    elw_seite.wait_for_function("() => document.querySelector('audio').readyState >= 1")
    elw_seite.get_by_text("Spracherkennung (Rohtext)").click()
    expect(elw_seite.get_by_text("Modell: fake")).to_be_visible()


# --- Filter ---


@pytest.fixture
def mit_nachrichten(elw_seite, server):
    brand = ApiMelder(server, "A", "EA Brand")
    wasser = ApiMelder(server, "B", "EA Wasserversorgung")
    brand.sende("Feuer im Keller", an="Einsatzleitung")
    brand.sende("Keller geräumt", an="Polizei")
    wasser.sende("Wasser läuft", an="Einsatzleitung")
    expect(zeilen(elw_seite)).to_have_count(3)
    return elw_seite


def test_filter_kombinieren(mit_nachrichten):
    page = mit_nachrichten
    filter_auswahl(page, "Von").select_option("EA Brand")
    expect(zeilen(page)).to_have_count(2)
    filter_auswahl(page, "An").select_option("Polizei")
    expect(zeilen(page)).to_have_count(1)
    expect(zeilen(page)).to_contain_text("Keller geräumt")
    expect(page.get_by_text("1 von 3")).to_be_visible()


def test_suche_ignoriert_gross_kleinschreibung_und_kombiniert_woerter(mit_nachrichten):
    page = mit_nachrichten
    suche = page.get_by_label("Suchen")
    suche.fill("KELLER brand")
    expect(zeilen(page)).to_have_count(2)
    suche.fill("keller GERÄUMT")
    expect(zeilen(page)).to_have_count(1)
    suche.fill("3")  # laufende Nummer
    expect(zeilen(page)).to_contain_text("Wasser läuft")


def test_filter_status_offen(mit_nachrichten):
    page = mit_nachrichten
    zeilen(page).first.click()
    status_setzen(page, "erledigt")
    expect(zeilen(page).first.get_by_test_id("status")).to_have_text("erledigt")
    gruppe = page.get_by_role("group", name="Status", exact=True)
    gruppe.get_by_role("button", name="offen").click()
    expect(zeilen(page)).to_have_count(2)
    gruppe.get_by_role("button", name="erledigt").click()
    expect(zeilen(page)).to_have_count(1)


def test_kein_treffer_und_zuruecksetzen(mit_nachrichten):
    page = mit_nachrichten
    page.get_by_label("Suchen").fill("gibtsnicht")
    expect(page.get_by_text("Keine Nachricht passt zum Filter.")).to_be_visible()
    page.get_by_role("button", name="Filter zurücksetzen").click()
    expect(zeilen(page)).to_have_count(3)
    expect(page.get_by_label("Suchen")).to_have_value("")


def test_zeitraum_in_der_zukunft_ergibt_keinen_treffer(mit_nachrichten):
    mit_nachrichten.get_by_label("Eingang ab").fill("2099-01-01T00:00")
    expect(zeilen(mit_nachrichten)).to_have_count(0)


def test_neue_nachricht_bei_aktivem_filter(mit_nachrichten, server):
    page = mit_nachrichten
    page.get_by_label("Suchen").fill("Keller")
    expect(zeilen(page)).to_have_count(2)
    melder = ApiMelder(server, "C", "EA Atemschutz")
    melder.sende("Trupp zurück")  # passt nicht
    expect(page.get_by_text("2 von 4")).to_be_visible()
    melder.sende("Trupp im Keller")  # passt
    expect(zeilen(page)).to_have_count(3)
    expect(page.get_by_text("3 von 5")).to_be_visible()
    expect(page.get_by_role("heading", name="Eingang")).to_contain_text("(5, 5 neu)")


# --- Mengen und Längen ---


def test_500_nachrichten(elw_seite):
    with new_session() as db:
        anmeldung = db.query(Anmeldung).filter(Anmeldung.rolle == Rolle.ELW).one()
        for i in range(500):
            message_service.create_nachricht(db, anmeldung, NachrichtCreate(an="ELW", inhalt=f"Meldung {i}"))
    elw_seite.reload()
    expect(zeilen(elw_seite)).to_have_count(500, timeout=15_000)
    elw_seite.get_by_label("Suchen").fill("Meldung 499")
    expect(zeilen(elw_seite)).to_have_count(2)  # Inhalt „Meldung 499“ und laufende Nummer 499


def test_sehr_langer_inhalt_sprengt_das_layout_nicht(elw_seite, beobachter_seite, api_melder):
    api_melder.sende("Wort" * 1250)  # 5000 Zeichen ohne Umbruchmöglichkeit
    zeilen(elw_seite).first.click()
    expect(elw_seite.locator(".inhalt-voll")).to_be_visible()
    for page in (elw_seite, beobachter_seite):
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    beobachter_seite.get_by_test_id("nachricht-karte").click()
    expect(beobachter_seite.locator(".inhalt-voll")).to_be_visible()
    assert beobachter_seite.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


def test_mehrere_melder_gleichzeitig(elw_seite, handy):
    seiten = []
    for i in range(3):
        page = handy()
        anmelden(page, "melder", f"Melder {i}", "EA Brand")
        page.get_by_label("An", exact=True).fill("ELW")
        page.get_by_label("Inhalt", exact=True).fill(f"Meldung von {i}")
        seiten.append(page)
    for page in seiten:
        page.get_by_role("button", name="Absenden").click()
    for page in seiten:
        expect(page.get_by_role("status")).to_contain_text("übermittelt")
    expect(zeilen(elw_seite)).to_have_count(3)
    assert sorted(zeilen(elw_seite).locator("td.nr").all_inner_texts()) == ["1", "2", "3"]


# --- Verbindung und Sitzung ---


@pytest.fixture
def erlaube_trennung(waechter):
    waechter.erlaube("WebSocket connection")
    waechter.erlaube("ERR_CONNECTION_REFUSED")
    waechter.erlaube(r"status of 401")


def test_server_neustart_holt_verpasstes_nach(elw_seite, server, erlaube_trennung):
    erzeuge_nachrichten("Vor dem Ausfall")
    elw_seite.reload()
    expect(zeilen(elw_seite)).to_have_count(1)
    server.stop()
    expect(elw_seite.get_by_test_id("verbindung")).to_have_text("● getrennt")
    erzeuge_nachrichten("Während des Ausfalls")
    server.start()
    expect(elw_seite.get_by_test_id("verbindung")).to_have_text("● live", timeout=15_000)
    expect(zeilen(elw_seite)).to_have_count(2)
    expect(zeilen(elw_seite).first).to_contain_text("Während des Ausfalls")
    expect(zeilen(elw_seite).first).to_have_class("neu")
    expect(elw_seite.get_by_role("heading", name="Eingang")).to_contain_text("(2, 1 neu)")


def test_abgelaufene_sitzung_fuehrt_nach_neustart_zum_login(elw_seite, server, erlaube_trennung):
    server.stop()
    beende_sitzungen()
    server.start()
    expect(elw_seite.get_by_role("heading", name=LOGIN)).to_be_visible(timeout=15_000)
    expect(elw_seite.get_by_text("Anmeldung abgelaufen")).to_be_visible()


def test_abgelaufene_sitzung_fuehrt_bei_neuer_nachricht_zum_login(elw_seite, server, erlaube_trennung):
    beende_sitzungen()
    ApiMelder(server, "Neu", "EA Brand").sende("Geht nur an gültige Anmeldungen")
    expect(elw_seite.get_by_role("heading", name=LOGIN)).to_be_visible(timeout=15_000)
    expect(zeilen(elw_seite)).to_have_count(0)


def test_abmelden_im_zweiten_tab_beendet_den_ersten(elw_seite, erlaube_trennung):
    tab2 = elw_seite.context.new_page()
    tab2.goto("/elw/")
    tab2.get_by_role("button", name="Abmelden").click()
    expect(elw_seite.get_by_role("heading", name=LOGIN)).to_be_visible(timeout=15_000)


def test_status_setzen_nach_ablauf_fuehrt_zum_login(elw_seite, api_melder, erlaube_trennung):
    api_melder.sende("Status bitte")
    zeilen(elw_seite).first.click()
    expect(elw_seite.locator(".audit li")).to_have_count(1)
    beende_sitzungen()
    status_setzen(elw_seite, "erledigt")
    expect(elw_seite.get_by_role("heading", name=LOGIN)).to_be_visible()


def test_uebersicht_der_anmeldungen(elw_seite, melder_seite):
    elw_seite.get_by_role("button", name="Angemeldet").click()
    panel = elw_seite.locator("aside.panel")
    expect(panel).to_contain_text("Angemeldet (2)")
    expect(panel).to_contain_text("Max Melder")
    expect(panel).to_contain_text("Erika ELW")
    panel.get_by_role("button", name="Schließen").click()
    expect(panel).to_have_count(0)


def test_gesendet_und_elw_zeigen_dieselbe_nummer(melder_seite, elw_seite):
    sende_text(melder_seite, "ELW", "Nummernabgleich")
    expect(zeilen(elw_seite).locator("td.nr")).to_have_text("1")
    expect(melder_seite.locator(".gesendet")).to_contain_text("Nr. 1")
