import pytest
from playwright.sync_api import expect

from app.db import new_session
from app.models import Nachricht
from app.services import ablage
from tests.ui.conftest import anmelden, beende_sitzungen, sende_text, spreche

pytestmark = pytest.mark.ui


def anzahl() -> int:
    with new_session() as db:
        return db.query(Nachricht).count()


def felder(page):
    return page.get_by_label("An", exact=True), page.get_by_label("Inhalt", exact=True), page.get_by_role("button", name="Absenden")


def test_absenden_erst_bei_gueltigen_feldern(melder_seite):
    an, inhalt, absenden = felder(melder_seite)
    expect(absenden).to_be_disabled()
    an.fill("Einsatzleitung")
    expect(absenden).to_be_disabled()
    inhalt.fill("   ")
    expect(absenden).to_be_disabled()
    inhalt.fill("Lage stabil")
    expect(absenden).to_be_enabled()
    an.fill("  ")
    expect(absenden).to_be_disabled()


def test_enter_sendet_nur_gueltige_formulare(melder_seite):
    an, inhalt, _ = felder(melder_seite)
    an.fill("Einsatzleitung")
    an.press("Enter")
    expect(melder_seite.get_by_role("status")).to_have_count(0)
    inhalt.fill("Lage stabil")
    an.press("Enter")
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    assert anzahl() == 1


def test_doppelklick_ergibt_eine_nachricht(melder_seite):
    an, inhalt, absenden = felder(melder_seite)
    an.fill("Einsatzleitung")
    inhalt.fill("Lage stabil")
    absenden.dblclick()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    assert anzahl() == 1


def test_bestaetigung_leert_das_formular_und_merkt_den_empfaenger(melder_seite):
    sende_text(melder_seite, "Einsatzleitung", "Lage stabil")
    status = melder_seite.get_by_role("status")
    expect(status).to_contain_text("Nachricht Nr. 1 übermittelt")
    expect(status).to_contain_text("an Einsatzleitung")
    an, inhalt, absenden = felder(melder_seite)
    expect(an).to_have_value("")
    expect(inhalt).to_have_value("")
    expect(absenden).to_be_disabled()

    melder_seite.get_by_role("button", name="Einsatzleitung", exact=True).click()
    expect(an).to_have_value("Einsatzleitung")
    expect(melder_seite.get_by_role("heading", name="Gesendet")).to_be_visible()
    melder_seite.get_by_role("button", name="OK").click()
    expect(status).to_have_count(0)


def test_eigene_funktion_wird_nicht_als_empfaenger_vorgeschlagen(melder_seite):
    sende_text(melder_seite, "EA Brand", "An mich selbst")
    expect(melder_seite.locator("form .chips .chip")).to_have_count(0)


def test_gesendete_bleiben_nach_reload(melder_seite):
    sende_text(melder_seite, "ELW", "Bleibt sichtbar")
    melder_seite.reload()
    expect(melder_seite.locator(".gesendet")).to_contain_text("Bleibt sichtbar")


def test_netzfehler_text_bleibt_und_erneutes_senden_klappt(melder_seite, waechter):
    waechter.erlaube("ERR_FAILED")
    melder_seite.route("**/api/messages", lambda r: r.abort(), times=1)
    an, inhalt, absenden = felder(melder_seite)
    an.fill("ELW")
    inhalt.fill("Wichtige Meldung")
    absenden.click()
    expect(melder_seite.get_by_text("Nicht übermittelt: Keine Verbindung zum ELW")).to_be_visible()
    expect(inhalt).to_have_value("Wichtige Meldung")
    absenden.click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    assert anzahl() == 1


def test_nas_fehler_text_bleibt_und_erneutes_senden_klappt(melder_seite, waechter, monkeypatch):
    waechter.erlaube("status of 503")

    def kaputt(*_a, **_kw):
        raise OSError("NAS weg")

    monkeypatch.setattr(ablage, "schreibe_nachricht", kaputt)
    an, inhalt, absenden = felder(melder_seite)
    an.fill("ELW")
    inhalt.fill("Wichtige Meldung")
    absenden.click()
    expect(melder_seite.get_by_text("Einsatzablage nicht beschreibbar")).to_be_visible()
    expect(inhalt).to_have_value("Wichtige Meldung")
    assert anzahl() == 0

    monkeypatch.undo()
    absenden.click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    assert anzahl() == 1


def test_verlorene_antwort_ergibt_keine_dublette(melder_seite, waechter):
    waechter.erlaube("ERR_FAILED")

    def antwort_geht_verloren(route):
        route.fetch()  # der Server speichert
        route.abort()

    melder_seite.route("**/api/messages", antwort_geht_verloren, times=1)
    an, inhalt, absenden = felder(melder_seite)
    an.fill("ELW")
    inhalt.fill("Einmal bitte")
    absenden.click()
    expect(melder_seite.get_by_text("Nicht übermittelt")).to_be_visible()
    assert anzahl() == 1
    absenden.click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    assert anzahl() == 1


SCHAD = '<img src=x onerror="window.__xss=1"><script>window.__xss=1</script>'


def test_html_wird_nur_als_text_angezeigt(melder_seite, elw_seite):
    sende_text(melder_seite, SCHAD[:100], SCHAD)
    zeile = elw_seite.get_by_test_id("nachricht-zeile")
    expect(zeile).to_contain_text("<script>")
    zeile.click()
    expect(elw_seite.locator(".inhalt-voll")).to_have_text(SCHAD)
    expect(melder_seite.locator(".gesendet p")).to_have_text(SCHAD)
    for seite in (melder_seite, elw_seite):
        assert seite.evaluate("window.__xss") is None
        assert seite.locator("img[src='x']").count() == 0


def test_emoji_und_zeilenumbrueche_bleiben_erhalten(melder_seite, elw_seite):
    text = "Feuer 🔥 aus\nZeile zwei\n\nÄußerst ß"
    sende_text(melder_seite, "ELW", text)
    elw_seite.get_by_test_id("nachricht-zeile").click()
    assert elw_seite.locator(".inhalt-voll").evaluate("e => e.textContent") == text
    assert elw_seite.locator(".inhalt-voll").evaluate("e => getComputedStyle(e).whiteSpace") == "pre-wrap"


def test_maximale_laenge(melder_seite, waechter):
    waechter.erlaube("status of 422")
    an, inhalt, absenden = felder(melder_seite)
    an.fill("ELW")
    inhalt.fill("x" * 5001)
    absenden.click()
    expect(melder_seite.get_by_text("Eingabe ungültig")).to_be_visible()
    expect(inhalt).to_have_value("x" * 5001)
    inhalt.fill("x" * 5000)
    absenden.click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")


def test_elw_erfasst_ueber_die_melder_ansicht(elw_seite, api_melder):
    with elw_seite.expect_popup() as popup:
        elw_seite.get_by_role("link", name="Nachricht erfassen").click()
    seite = popup.value
    expect(seite.locator(".von strong")).to_have_text("ELW")
    api_melder.sende("Fremde Nachricht")
    sende_text(seite, "EA Brand", "Per Funk: Lage stabil")
    expect(seite.locator(".gesendet article")).to_have_count(1)
    expect(elw_seite.get_by_test_id("nachricht-zeile")).to_have_count(2)


# --- Abgelaufene Sitzung (F7) ---


LOGIN = "Anmelden als Melder"


def neu_anmelden(page) -> None:
    expect(page.get_by_role("heading", name=LOGIN)).to_be_visible()
    expect(page.get_by_text("Anmeldung abgelaufen")).to_be_visible()
    page.get_by_label("Name").fill("Max Melder")
    page.get_by_label("Funktion").fill("EA Brand")
    page.get_by_role("button", name="Anmelden", exact=True).click()


@pytest.fixture
def erlaube_401(waechter):
    waechter.erlaube(r"status of 401")


def test_sitzung_laeuft_beim_tippen_ab_text_bleibt(melder_seite, erlaube_401):
    an, inhalt, absenden = felder(melder_seite)
    an.fill("Einsatzleitung")
    inhalt.fill("Nicht verlieren")
    beende_sitzungen()
    absenden.click()
    neu_anmelden(melder_seite)
    expect(inhalt).to_have_value("Nicht verlieren")
    expect(an).to_have_value("Einsatzleitung")
    expect(melder_seite.get_by_text("Nicht übermittelt")).to_have_count(0)
    absenden.click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    assert anzahl() == 1


def test_sitzung_laeuft_bei_der_spracherkennung_ab(melder_seite, erlaube_401):
    an, inhalt, _ = felder(melder_seite)
    inhalt.fill("Schon getippt")
    beende_sitzungen()
    spreche(melder_seite, "Empfänger sprechen")
    neu_anmelden(melder_seite)
    expect(inhalt).to_have_value("Schon getippt")


def test_sitzung_beim_laden_der_gesendeten_abgelaufen(melder_seite, erlaube_401):
    melder_seite.route("**/api/messages?nur_eigene=true", lambda r: r.fulfill(status=401, json={"detail": "Nicht angemeldet"}))
    melder_seite.reload()
    expect(melder_seite.get_by_role("heading", name=LOGIN)).to_be_visible()


def test_nach_neuer_anmeldung_nur_die_eigenen_gesendeten(melder_seite, erlaube_401):
    """Meldet sich jemand anderes an, darf die Liste der vorherigen Anmeldung nicht stehen bleiben."""
    sende_text(melder_seite, "ELW", "Von der alten Anmeldung")
    beende_sitzungen()
    melder_seite.get_by_label("An", exact=True).fill("ELW")
    melder_seite.get_by_label("Inhalt", exact=True).fill("x")
    melder_seite.get_by_role("button", name="Absenden").click()
    neu_anmelden(melder_seite)
    expect(melder_seite.get_by_role("button", name="Absenden")).to_be_enabled()
    expect(melder_seite.locator(".gesendet")).to_have_count(0)


def test_abmelden_verwirft_das_formular(melder_seite):
    """Anders als beim Ablauf: Wer sich selbst abmeldet, gibt das Handy vielleicht weiter."""
    _, inhalt, _ = felder(melder_seite)
    inhalt.fill("Vertraulich")
    melder_seite.get_by_role("button", name="Abmelden").click()
    anmelden(melder_seite, "melder", "Nächste Person", "EA Brand")
    expect(inhalt).to_have_value("")
