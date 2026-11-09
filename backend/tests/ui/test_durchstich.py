"""Der wichtigste Ablauf einmal komplett: Melder spricht, ELW sieht es live."""

import pytest
from playwright.sync_api import expect

from app.config import get_settings
from app.db import new_session
from app.models import AuditEvent, Nachricht
from tests.ui.conftest import spreche

pytestmark = pytest.mark.ui


def test_melder_spricht_und_elw_sieht_live(elw_seite, melder_seite, stt):
    stt.antworten = ["Einsatzleitung", "Feuer unter Kontrolle."]

    spreche(melder_seite, "Empfänger sprechen")
    expect(melder_seite.get_by_label("An", exact=True)).to_have_value("Einsatzleitung")
    spreche(melder_seite, "Inhalt sprechen")
    expect(melder_seite.get_by_label("Inhalt", exact=True)).to_have_value("Feuer unter Kontrolle.")
    melder_seite.get_by_role("button", name="Absenden").click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nachricht Nr. 1 übermittelt")

    zeile = elw_seite.get_by_test_id("nachricht-zeile")
    expect(zeile).to_have_count(1)
    expect(zeile).to_contain_text("Feuer unter Kontrolle.")
    expect(zeile).to_contain_text("EA Brand")

    assert len(stt.calls) == 2 and all(audio for audio, _ in stt.calls)
    with new_session() as db:
        n = db.query(Nachricht).one()
        assert n.eingabe["inhalt"]["art"] == "sprache"
        assert [a.art for a in n.anhaenge] == ["audio", "audio"]
        assert db.query(AuditEvent).count() == 1
        ordner = get_settings().ablage_root / n.ablage_ordner
    assert all((ordner / a.dateiname).stat().st_size > 0 for a in n.anhaenge)
