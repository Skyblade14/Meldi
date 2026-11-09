import pytest
from playwright.sync_api import expect

from tests.ui.conftest import anmelden, beende_sitzungen, erzeuge_nachrichten, filter_auswahl

pytestmark = pytest.mark.ui


def karten(page):
    return page.get_by_test_id("nachricht-karte")


def test_keine_status_und_erfassen_funktion(beobachter_seite, api_melder):
    api_melder.sende("Nur lesen")
    karten(beobachter_seite).click()
    expect(beobachter_seite.locator(".inhalt-voll")).to_have_text("Nur lesen")
    expect(beobachter_seite.get_by_role("group", name="Status setzen")).to_have_count(0)
    expect(beobachter_seite.get_by_role("link", name="Nachricht erfassen")).to_have_count(0)
    expect(beobachter_seite.get_by_role("button", name="Absenden")).to_have_count(0)


def test_live_updates_und_neu_zaehler(beobachter_seite, api_melder):
    expect(beobachter_seite.get_by_text("Noch keine Nachrichten.")).to_be_visible()
    api_melder.sende("Live zum Handy")
    expect(karten(beobachter_seite)).to_contain_text("Live zum Handy")
    expect(beobachter_seite.get_by_text("1 neu")).to_be_visible()
    expect(karten(beobachter_seite)).to_have_class("karte card neu")


def test_filter_auf_dem_handy(beobachter_seite, api_melder):
    api_melder.sende("Feuer im Keller")
    api_melder.sende("Wasser läuft", an="Polizei")
    expect(karten(beobachter_seite)).to_have_count(2)

    expect(beobachter_seite.get_by_label("Von")).to_be_hidden()  # eingeklappt
    beobachter_seite.get_by_role("button", name="Filter").click()
    filter_auswahl(beobachter_seite, "An").select_option("Polizei")
    expect(karten(beobachter_seite)).to_have_count(1)
    expect(beobachter_seite.get_by_role("button", name="Filter (1)")).to_be_visible()
    beobachter_seite.get_by_role("button", name="Filter zurücksetzen").click()
    beobachter_seite.get_by_label("Suchen").fill("keller")
    expect(karten(beobachter_seite)).to_contain_text("Feuer im Keller")


def test_scrollposition_bleibt_bei_neuen_nachrichten(beobachter_seite, api_melder):
    erzeuge_nachrichten(*[f"Meldung {i}" for i in range(30)])
    beobachter_seite.reload()
    expect(karten(beobachter_seite)).to_have_count(30)
    karte = karten(beobachter_seite).nth(15)
    karte.scroll_into_view_if_needed()
    vorher = karte.bounding_box()["y"]
    api_melder.sende("Neu oben")
    expect(karten(beobachter_seite)).to_have_count(31)
    nachher = karten(beobachter_seite).nth(16).bounding_box()["y"]
    assert abs(nachher - vorher) <= 2


def test_zurueck_taste_schliesst_das_detail_und_stellt_die_position_her(beobachter_seite):
    erzeuge_nachrichten(*[f"Meldung {i}" for i in range(30)])
    beobachter_seite.reload()
    expect(karten(beobachter_seite)).to_have_count(30)
    karten(beobachter_seite).nth(15).scroll_into_view_if_needed()
    y = beobachter_seite.evaluate("window.scrollY")
    assert y > 0
    karten(beobachter_seite).nth(15).click()
    expect(beobachter_seite.locator(".inhalt-voll")).to_be_visible()
    beobachter_seite.go_back()
    expect(beobachter_seite.locator(".inhalt-voll")).to_have_count(0)
    expect(karten(beobachter_seite).nth(15)).to_be_visible()
    beobachter_seite.wait_for_function("(y) => Math.abs(window.scrollY - y) <= 2", arg=y)


def test_detail_zeigt_status_live(beobachter_seite, api_melder, desktop):
    api_melder.sende("Status beobachten")
    karten(beobachter_seite).click()
    expect(beobachter_seite.get_by_test_id("detail-status")).to_have_text("neu")
    elw = desktop()
    anmelden(elw, "elw", "Erika ELW")
    elw.get_by_test_id("nachricht-zeile").click()
    elw.get_by_role("group", name="Status setzen").get_by_role("button", name="erledigt").click()
    expect(beobachter_seite.get_by_test_id("detail-status")).to_have_text("erledigt")


def test_abgelaufene_sitzung_fuehrt_zum_login(beobachter_seite, server, waechter):
    waechter.erlaube("WebSocket connection")
    waechter.erlaube("ERR_CONNECTION_REFUSED")
    waechter.erlaube(r"status of 401")
    server.stop()
    beende_sitzungen()
    server.start()
    expect(beobachter_seite.get_by_role("heading", name="Beobachter – Anmeldung")).to_be_visible(timeout=15_000)


def test_alle_zustaende_auf_handygroesse(beobachter_seite, api_melder, waechter):
    """Der Wächter prüft sonst nur den Endzustand eines Tests."""
    api_melder.sende("Prüfung")
    expect(karten(beobachter_seite)).to_have_count(1)
    beobachter_seite.get_by_role("button", name="Filter").click()
    waechter.pruefe_handy(beobachter_seite)
    karten(beobachter_seite).click()
    expect(beobachter_seite.locator(".inhalt-voll")).to_be_visible()
    waechter.pruefe_handy(beobachter_seite)
