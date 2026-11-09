import pytest
from PIL import Image
from playwright.sync_api import expect

from app.config import get_settings
from app.db import new_session
from app.models import Nachricht
from tests.ui.conftest import jpeg, warte_bis

pytestmark = pytest.mark.ui

FOTO_INPUT = "input[type=file]"


def kacheln(page):
    return page.get_by_test_id("foto-kachel")


def absenden(page):
    return page.get_by_role("button", name="Absenden")


def fuelle_text(page) -> None:
    page.get_by_label("An", exact=True).fill("ELW")
    page.get_by_label("Inhalt", exact=True).fill("Lagebild")


def warte_auf_upload(page) -> None:
    expect(page.locator(".fotos .status")).to_have_count(0)


def gespeichert() -> tuple[Nachricht, list]:
    with new_session() as db:
        n = db.query(Nachricht).one()
        fotos = [a for a in n.anhaenge if a.art == "foto"]
    return n, fotos


def bild_aus_ablage(n, anhang) -> Image.Image:
    return Image.open(get_settings().ablage_root / n.ablage_ordner / anhang.dateiname)


def test_gps_kommt_an_und_grosse_fotos_werden_verkleinert(melder_seite, tmp_path):
    fuelle_text(melder_seite)
    melder_seite.set_input_files(FOTO_INPUT, jpeg(tmp_path / "gross.jpg", 4000, 3000, gps=True))
    warte_auf_upload(melder_seite)
    absenden(melder_seite).click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    n, fotos = gespeichert()
    assert len(fotos) == 1
    assert fotos[0].meta["gps"] == pytest.approx({"lat": 52.52, "lon": 13.405})
    assert bild_aus_ablage(n, fotos[0]).size == (2560, 1920)


def test_hochkant_foto_wird_gedreht(melder_seite, tmp_path):
    fuelle_text(melder_seite)
    melder_seite.set_input_files(FOTO_INPUT, jpeg(tmp_path / "hoch.jpg", 800, 600, orientierung=6))
    warte_auf_upload(melder_seite)
    absenden(melder_seite).click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    n, fotos = gespeichert()
    assert bild_aus_ablage(n, fotos[0]).size == (600, 800)


def test_limit_von_fuenf_fotos(melder_seite, tmp_path):
    for i in range(5):
        melder_seite.set_input_files(FOTO_INPUT, jpeg(tmp_path / f"{i}.jpg", 100, 100))
        expect(kacheln(melder_seite)).to_have_count(i + 1)
        warte_auf_upload(melder_seite)
    expect(melder_seite.get_by_role("button", name="Foto aufnehmen")).to_have_count(0)
    expect(melder_seite.get_by_text("(5/5)")).to_be_visible()


def test_kaputte_datei_zeigt_den_grund_am_knopf(melder_seite, tmp_path):
    kaputt = tmp_path / "kaputt.jpg"
    kaputt.write_bytes(b"das ist kein jpeg")
    fuelle_text(melder_seite)
    melder_seite.set_input_files(FOTO_INPUT, kaputt)
    expect(melder_seite.get_by_text("Foto nicht lesbar")).to_be_visible()
    expect(absenden(melder_seite)).to_be_disabled()
    expect(melder_seite.get_by_text("Fehlerhaftes Foto entfernen")).to_be_visible()
    melder_seite.get_by_role("button", name="Foto entfernen").click()
    expect(absenden(melder_seite)).to_be_enabled()
    expect(melder_seite.get_by_text("Fehlerhaftes Foto entfernen")).to_have_count(0)
    absenden(melder_seite).click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")


def test_upload_fehler_mit_erneut(melder_seite, tmp_path, waechter):
    waechter.erlaube("ERR_FAILED")
    melder_seite.route("**/api/uploads/foto", lambda r: r.abort(), times=1)
    fuelle_text(melder_seite)
    melder_seite.set_input_files(FOTO_INPUT, jpeg(tmp_path / "a.jpg"))
    erneut = melder_seite.get_by_role("button", name="erneut")
    expect(erneut).to_be_visible()
    expect(absenden(melder_seite)).to_be_disabled()
    erneut.click()
    warte_auf_upload(melder_seite)
    expect(absenden(melder_seite)).to_be_enabled()
    absenden(melder_seite).click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    assert len(gespeichert()[1]) == 1


def halte_upload(page) -> list:
    gehalten: list = []
    page.route("**/api/uploads/foto", lambda route: gehalten.append(route))
    return gehalten


def test_absenden_gesperrt_solange_ein_foto_laedt(melder_seite, tmp_path):
    gehalten = halte_upload(melder_seite)
    fuelle_text(melder_seite)
    melder_seite.set_input_files(FOTO_INPUT, jpeg(tmp_path / "a.jpg"))
    expect(melder_seite.get_by_text("lädt …")).to_be_visible()
    expect(absenden(melder_seite)).to_be_disabled()
    expect(melder_seite.get_by_text("Foto wird noch hochgeladen")).to_be_visible()
    warte_bis(melder_seite, lambda: gehalten)
    gehalten[0].continue_()
    warte_auf_upload(melder_seite)
    expect(absenden(melder_seite)).to_be_enabled()


def test_entfernen_waehrend_des_uploads(melder_seite, tmp_path):
    gehalten = halte_upload(melder_seite)
    fuelle_text(melder_seite)
    melder_seite.set_input_files(FOTO_INPUT, jpeg(tmp_path / "a.jpg"))
    warte_bis(melder_seite, lambda: gehalten)
    melder_seite.get_by_role("button", name="Foto entfernen").click()
    expect(kacheln(melder_seite)).to_have_count(0)
    gehalten[0].continue_()
    absenden(melder_seite).click()
    expect(melder_seite.get_by_role("status")).to_contain_text("Nr. 1")
    assert gespeichert()[1] == []
