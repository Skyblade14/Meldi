import pytest
from playwright.sync_api import expect

from app.db import new_session, utcnow
from app.models import Anmeldung, Einsatz
from tests.ui.conftest import anmelden

pytestmark = pytest.mark.ui

ANMELDEN = {"name": "Anmelden", "exact": True}


@pytest.mark.parametrize(
    ("kachel", "pfad", "titel"),
    [("Melder", "/melder/", "Anmelden als Melder"), ("ELW", "/elw/", "ELW – Anmeldung"), ("Beobachter", "/beobachter/", "Beobachter – Anmeldung")],
)
def test_kachel_fuehrt_zur_ansicht(handy, server, kachel, pfad, titel):
    page = handy()
    page.goto("/")
    page.get_by_role("link", name=kachel).click()
    expect(page).to_have_url(server.url + pfad)
    expect(page.get_by_role("heading", name=titel)).to_be_visible()


@pytest.mark.parametrize(
    ("ansicht", "funktion", "zu_sehen"),
    [("melder", "EA Brand", "Absenden"), ("elw", None, "Angemeldet"), ("beobachter", None, "Abmelden")],
)
def test_reload_haelt_die_anmeldung(desktop, ansicht, funktion, zu_sehen):
    page = desktop()
    anmelden(page, ansicht, "Rita Reload", funktion)
    page.reload()
    expect(page.get_by_role("button", name=zu_sehen)).to_be_visible()
    expect(page.get_by_role("button", **ANMELDEN)).to_have_count(0)


def test_zurueck_taste_nach_abmelden_zeigt_keine_daten(desktop):
    page = desktop()
    page.goto("/")
    page.get_by_role("link", name="ELW").click()
    page.get_by_label("Name").fill("Erika ELW")
    page.get_by_role("button", **ANMELDEN).click()
    page.get_by_role("button", name="Abmelden").click()
    expect(page.get_by_role("button", **ANMELDEN)).to_be_visible()
    page.go_back()
    page.go_forward()
    expect(page.get_by_role("heading", name="ELW – Anmeldung")).to_be_visible()
    expect(page.get_by_test_id("nachricht-zeile")).to_have_count(0)


@pytest.fixture
def erlaube_422(waechter):
    waechter.erlaube(r"status of 422 ")


def test_name_nur_aus_leerzeichen(handy, erlaube_422):
    page = handy()
    page.goto("/beobachter/")
    page.get_by_label("Name").fill("   ")
    page.get_by_role("button", **ANMELDEN).click()
    expect(page.get_by_text("Eingabe ungültig")).to_be_visible()
    expect(page.get_by_role("button", **ANMELDEN)).to_be_enabled()


def test_name_zu_lang(handy, erlaube_422):
    page = handy()
    page.goto("/beobachter/")
    page.get_by_label("Name").fill("x" * 101)
    page.get_by_role("button", **ANMELDEN).click()
    expect(page.get_by_text("Eingabe ungültig")).to_be_visible()


def test_umlaute_und_langer_name(handy, elw_seite, api_melder):
    page = handy()
    name = "Jürgen-Maximilian Größenwahn-Äußerlich von und zu Überlingen am See"
    anmelden(page, "melder", name, "EA Brand")
    expect(page.get_by_text(f"EA Brand · {name}")).to_be_attached()
    page.get_by_label("An", exact=True).fill("ELW")
    page.get_by_label("Inhalt", exact=True).fill("Straße frei")
    page.get_by_role("button", name="Absenden").click()
    elw_seite.get_by_test_id("nachricht-zeile").click()
    expect(elw_seite.get_by_text(name, exact=True)).to_be_visible()


def test_frei_getippte_funktion(handy):
    page = handy()
    anmelden(page, "melder", "Dora Drohne", "Drohnentrupp")
    expect(page.locator(".von strong")).to_have_text("Drohnentrupp")


def test_funktion_per_chip_waehlen(handy):
    page = handy()
    page.goto("/melder/")
    page.get_by_label("Name").fill("Chip Wahl")
    page.get_by_role("button", name="EA Atemschutz").click()
    expect(page.get_by_label("Funktion")).to_have_value("EA Atemschutz")


def test_kein_aktiver_einsatz(handy, waechter):
    waechter.erlaube(r"status of 401 .*/api/auth/login")
    with new_session() as db:
        for e in db.query(Einsatz).all():
            e.ende = utcnow()
        db.commit()
    page = handy()
    page.goto("/beobachter/")
    page.get_by_label("Name").fill("Bea")
    page.get_by_role("button", **ANMELDEN).click()
    expect(page.get_by_text("Kein aktiver Einsatz")).to_be_visible()


def test_rollenwechsel_beendet_die_alte_anmeldung(desktop):
    page = desktop()
    anmelden(page, "melder", "Wechsel Wanda", "EA Brand")
    page.goto("/elw/")
    page.get_by_label("Name").fill("Wechsel Wanda")
    page.get_by_role("button", **ANMELDEN).click()
    expect(page.get_by_role("button", name="Angemeldet")).to_be_visible()
    with new_session() as db:
        status = {a.rolle.value: a.abgemeldet_at is not None for a in db.query(Anmeldung).all()}
    assert status == {"melder": True, "elw": False}


def test_rollenwechsel_im_zweiten_tab_beendet_die_lese_ansicht(beobachter_seite, waechter):
    waechter.erlaube("WebSocket connection")
    tab2 = beobachter_seite.context.new_page()
    anmelden(tab2, "melder", "Bea Beobachter", "EA Brand")
    expect(beobachter_seite.get_by_role("heading", name="Beobachter – Anmeldung")).to_be_visible(timeout=15_000)


def test_beobachter_landet_auf_melder_beim_login(beobachter_seite):
    beobachter_seite.goto("/melder/")
    expect(beobachter_seite.get_by_role("heading", name="Anmelden als Melder")).to_be_visible()


def test_melder_kommt_nicht_in_die_elw_ansicht(melder_seite):
    melder_seite.goto("/elw/")
    expect(melder_seite.get_by_role("heading", name="ELW – Anmeldung")).to_be_visible()
    melder_seite.goto("/beobachter/")
    expect(melder_seite.get_by_role("heading", name="Beobachter – Anmeldung")).to_be_visible()
