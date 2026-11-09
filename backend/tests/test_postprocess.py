import pytest

from app.services.seed import STANDARD_FUNKTIONEN
from app.stt.base import Segment
from app.stt.postprocess import clean_text, entferne_wiederholungen, is_hallucinated_segment, match_funktion

FUNKTIONEN = [(i, n, [a.strip() for a in al.split(",") if a.strip()]) for i, (n, al) in enumerate(STANDARD_FUNKTIONEN)]


def seg(text: str, logprob: float = -0.2, no_speech: float = 0.05) -> Segment:
    return Segment(0, 1, text, logprob, no_speech)


@pytest.mark.parametrize(
    "text",
    ["Untertitel im Auftrag des ZDF, 2021", "Untertitelung des ZDF für funk, 2017", "Vielen Dank fürs Zuschauen!", "..."],
)
def test_bekannte_halluzinationen_werden_verworfen(text):
    assert is_hallucinated_segment(seg(text))


def test_unsicheres_segment_ohne_sprache_wird_verworfen():
    assert is_hallucinated_segment(seg("Hallo", logprob=-1.4, no_speech=0.8))


def test_normale_meldung_bleibt():
    assert not is_hallucinated_segment(seg("Feuer unter Kontrolle."))


def test_abkuerzungen_werden_grossgeschrieben():
    assert clean_text("  Benötigen  einen  Rtw und eine dlk ") == "Benötigen einen RTW und eine DLK"


@pytest.mark.parametrize(
    ("gesprochen", "erwartet"),
    [
        ("Einsatzleitung.", "Einsatzleitung"),
        ("An die Einsatzleitung", "Einsatzleitung"),
        ("Einsatzabschnitt Brand", "EA Brand"),
        ("Abschnitt Wasser", "EA Wasserversorgung"),
        ("an den Einsatzabschnitt Atemschutz", "EA Atemschutz"),
        ("Einsatzleitwagen", "ELW"),
        ("Bereitstellungsraum", "Bereitstellungsraum"),
        ("Technische Hilfe", "EA Technische Hilfe"),
        ("Atemschutzüberwachung", "Atemschutzüberwachung"),
    ],
)
def test_empfaenger_zuordnung(gesprochen, erwartet):
    best = match_funktion(gesprochen, FUNKTIONEN)[0]
    assert best.name == erwartet
    assert best.score >= 80


def test_unbekannter_empfaenger_hat_niedrigen_score():
    assert match_funktion("Bürgermeister", FUNKTIONEN)[0].score < 80


def test_leerer_empfaenger():
    assert match_funktion("  . ", FUNKTIONEN) == []


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("Einsatzabschnitt, Brand, Einsatzabschnitt, Brand.", "Einsatzabschnitt, Brand."),
        ("Rettungsdienst, Rettungsdienst, Rettungsdienst, Rettungsdienst", "Rettungsdienst."),
        ("Rettungsdienst.", "Rettungsdienst."),
        ("EA Brand", "EA Brand"),
    ],
)
def test_entferne_wiederholungen(text, erwartet):
    assert entferne_wiederholungen(text) == erwartet
