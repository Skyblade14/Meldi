import pytest
from playwright.sync_api import expect

from app.db import new_session
from app.models import Nachricht
from tests.ui.conftest import anmelden, spreche

pytestmark = pytest.mark.ui

EMPFAENGER = "Empfänger sprechen"
INHALT = "Inhalt sprechen"


def an(page):
    return page.get_by_label("An", exact=True)


def inhalt(page):
    return page.get_by_label("Inhalt", exact=True)


def absenden(page):
    return page.get_by_role("button", name="Absenden")


def letzte() -> Nachricht:
    with new_session() as db:
        n = db.query(Nachricht).one()
        _ = n.anhaenge
        return n


def test_ablauf_aufnahme_erkennung_text(melder_seite, stt):
    stt.anhalten()
    stt.antworten = ["Feuer aus."]
    spreche(melder_seite, INHALT)
    knopf = melder_seite.locator(".rec-btn.processing")
    expect(knopf).to_contain_text("Erkenne")
    expect(knopf).to_be_disabled()
    stt.freigeben()
    expect(inhalt(melder_seite)).to_have_value("Feuer aus.")
    expect(melder_seite.get_by_text("erkannt in")).to_be_visible()
    expect(melder_seite.get_by_role("button", name=INHALT)).to_be_enabled()


def test_empfaenger_mit_hoher_uebereinstimmung_wird_uebernommen(melder_seite, stt):
    stt.antworten = ["Einsatzleitung"]
    spreche(melder_seite, EMPFAENGER)
    expect(an(melder_seite)).to_have_value("Einsatzleitung")
    # Weitere Treffer über 50 % bleiben als Alternative wählbar.
    melder_seite.get_by_role("button", name="ELW", exact=True).click()
    expect(an(melder_seite)).to_have_value("ELW")
    expect(melder_seite.get_by_text("Meinten Sie")).to_have_count(0)


def test_empfaenger_mit_niedriger_uebereinstimmung_fragt_nach(melder_seite, stt):
    stt.antworten = ["Atemschutz Trupp zwei."]
    spreche(melder_seite, EMPFAENGER)
    expect(an(melder_seite)).to_have_value("Atemschutz Trupp zwei")
    expect(melder_seite.get_by_text("Meinten Sie")).to_be_visible()
    melder_seite.get_by_role("button", name="EA Atemschutz", exact=True).click()
    expect(an(melder_seite)).to_have_value("EA Atemschutz")


def test_inhalt_in_etappen(melder_seite, stt):
    stt.antworten = ["Erste Etappe.", "Zweite Etappe."]
    an(melder_seite).fill("ELW")
    spreche(melder_seite, INHALT)
    expect(inhalt(melder_seite)).to_have_value("Erste Etappe.")
    spreche(melder_seite, INHALT)
    expect(inhalt(melder_seite)).to_have_value("Erste Etappe. Zweite Etappe.")
    absenden(melder_seite).click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    n = letzte()
    assert [a.feld for a in n.anhaenge] == ["inhalt", "inhalt"]
    assert n.eingabe["inhalt"]["rohtext"] == "Erste Etappe. Zweite Etappe."


def test_inhalt_leeren_verwirft_die_aufnahmen(melder_seite, stt):
    stt.antworten = ["Verworfen."]
    an(melder_seite).fill("ELW")
    spreche(melder_seite, INHALT)
    expect(inhalt(melder_seite)).to_have_value("Verworfen.")
    melder_seite.get_by_role("button", name="Inhalt leeren").click()
    expect(inhalt(melder_seite)).to_have_value("")
    inhalt(melder_seite).fill("Getippt")
    absenden(melder_seite).click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    n = letzte()
    assert n.anhaenge == []
    assert n.eingabe["inhalt"]["art"] == "text"


def test_nichts_erkannt(melder_seite, stt):
    stt.antworten = [""]
    spreche(melder_seite, INHALT)
    expect(melder_seite.get_by_text("Nichts erkannt")).to_be_visible()
    expect(inhalt(melder_seite)).to_have_value("")


def test_stt_ausfall_tippen_geht_weiter(melder_seite, stt, waechter):
    waechter.erlaube("status of 503")
    stt.antworten = [RuntimeError("Modell fehlt")]
    spreche(melder_seite, INHALT)
    expect(melder_seite.get_by_text("Spracherkennung nicht verfügbar – bitte tippen")).to_be_visible()
    an(melder_seite).fill("ELW")
    inhalt(melder_seite).fill("Getippt statt gesprochen")
    absenden(melder_seite).click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")


@pytest.mark.parametrize(
    ("fehler", "meldung"),
    [
        ("NotAllowedError", "Mikrofon-Zugriff verweigert"),
        ("NotFoundError", "Mikrofon konnte nicht gestartet werden"),
    ],
)
def test_mikrofon_nicht_nutzbar(handy, fehler, meldung):
    page = handy(
        # Init-Skripte laufen auch auf about:blank, dort gibt es keine mediaDevices.
        "if (navigator.mediaDevices) navigator.mediaDevices.getUserMedia = "
        f"() => Promise.reject(new DOMException('nein', '{fehler}'));"
    )
    anmelden(page, "melder", "Max Melder", "EA Brand")
    page.get_by_role("button", name=INHALT).click()
    expect(page.get_by_text(meldung)).to_be_visible()
    inhalt(page).fill("Tippen geht")
    expect(inhalt(page)).to_have_value("Tippen geht")


def test_browser_ohne_aufnahme(handy):
    page = handy("delete window.MediaRecorder;")
    anmelden(page, "melder", "Max Melder", "EA Brand")
    expect(page.get_by_text("unterstützt keine Audioaufnahme").first).to_be_visible()
    expect(page.get_by_role("button", name=INHALT)).to_be_disabled()


def test_auto_stopp_bei_stille(melder_seite, stt):
    stt.antworten = ["Automatisch gestoppt."]
    melder_seite.get_by_role("button", name=INHALT).click()
    expect(inhalt(melder_seite)).to_have_value("Automatisch gestoppt.", timeout=15_000)


def test_beide_mikrofon_knoepfe_gleichzeitig(melder_seite, stt):
    stt.antworten = ["Einsatzleitung", "Parallel gesprochen."]
    melder_seite.get_by_role("button", name=EMPFAENGER).click()
    melder_seite.get_by_role("button", name=INHALT).click()
    stopp = melder_seite.get_by_role("button", name="Aufnahme beenden")
    expect(stopp).to_have_count(2)
    stopp.first.click()
    expect(stopp).to_have_count(1)
    stopp.first.click()
    expect(an(melder_seite)).not_to_have_value("")
    expect(inhalt(melder_seite)).not_to_have_value("")


# --- Absenden während der Spracheingabe (F5) ---


def test_absenden_gesperrt_waehrend_der_erkennung(melder_seite, stt):
    an(melder_seite).fill("ELW")
    inhalt(melder_seite).fill("Erste Etappe.")
    expect(absenden(melder_seite)).to_be_enabled()
    stt.anhalten()
    stt.antworten = ["Zweite Etappe."]
    spreche(melder_seite, INHALT)
    expect(melder_seite.locator(".rec-btn.processing")).to_contain_text("Erkenne")
    expect(absenden(melder_seite)).to_be_disabled()
    expect(melder_seite.get_by_text("Spracheingabe läuft")).to_be_visible()
    stt.freigeben()
    expect(inhalt(melder_seite)).to_have_value("Erste Etappe. Zweite Etappe.")
    expect(absenden(melder_seite)).to_be_enabled()
    expect(melder_seite.get_by_text("Spracheingabe läuft")).to_have_count(0)


def test_absenden_gesperrt_waehrend_der_aufnahme(melder_seite):
    an(melder_seite).fill("ELW")
    inhalt(melder_seite).fill("Text")
    melder_seite.get_by_role("button", name=INHALT).click()
    expect(melder_seite.get_by_role("button", name="Aufnahme beenden")).to_be_visible()
    expect(absenden(melder_seite)).to_be_disabled()


MIKROFON_MERKEN = """
if (navigator.mediaDevices) {
  const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  window.__mikrofone = [];
  navigator.mediaDevices.getUserMedia = async (c) => { const s = await original(c); window.__mikrofone.push(s); return s; };
}
"""


def test_abmelden_waehrend_der_aufnahme_gibt_das_mikrofon_frei(handy):
    page = handy(MIKROFON_MERKEN)
    anmelden(page, "melder", "Max Melder", "EA Brand")
    page.get_by_role("button", name=INHALT).click()
    expect(page.get_by_role("button", name="Aufnahme beenden")).to_be_visible()
    assert page.evaluate("window.__mikrofone[0].getTracks()[0].readyState") == "live"
    page.get_by_role("button", name="Abmelden").click()
    expect(page.get_by_role("button", name="Anmelden", exact=True)).to_be_visible()
    page.wait_for_function("() => window.__mikrofone[0].getTracks().every((t) => t.readyState === 'ended')")
