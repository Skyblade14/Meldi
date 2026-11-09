"""Feuerwehr-Vokabular und feldspezifische Prompts für Whisper.

Whisper nutzt den `initial_prompt` als „vorherigen Text". Ein Prompt im Stil echter Meldungen
mit den richtigen Fachbegriffen erhöht die Chance, dass diese korrekt geschrieben werden.
"""

from app.stt.base import TranscribeHint

FACHBEGRIFFE = [
    "Einsatzleitung",
    "Einsatzabschnitt",
    "ELW",
    "HLF",
    "LF",
    "TLF",
    "DLK",
    "RW",
    "GW-L",
    "MTW",
    "RTW",
    "NEF",
    "KTW",
    "PA",
    "Atemschutz",
    "Atemschutzüberwachung",
    "Angriffstrupp",
    "Sicherheitstrupp",
    "Wassertrupp",
    "Innenangriff",
    "B-Rohr",
    "C-Rohr",
    "Hydrant",
    "Wasserversorgung",
    "Bereitstellungsraum",
    "Wärmebildkamera",
    "Lüfter",
    "Drehleiter",
    "Personenrettung",
    "Feuer aus",
    "unter Kontrolle",
    "Nachalarmierung",
]

# Großschreibung, die Whisper gelegentlich verliert („Rtw", „dlk").
ABKUERZUNGEN = ["ELW", "HLF", "LF", "TLF", "DLK", "RW", "MTW", "RTW", "NEF", "KTW", "PA", "GW-L", "EA", "EL", "THL", "BMA"]

INHALT_PROMPT = (
    "Lagemeldung: Zwei Trupps unter PA im Innenangriff, ein C-Rohr vorgenommen. "
    "RTW und NEF an der Einsatzstelle, DLK in Stellung. Wasserversorgung über Hydrant hergestellt. "
    "Benötigen weiteren Atemschutz und eine Wärmebildkamera im Bereitstellungsraum."
)


def hint_for_field(field: str, funktionen: list[str]) -> TranscribeHint:
    """`funktionen`: Namen UND gesprochene Varianten (Aliase) – fehlt z.B. „Einsatzleitwagen“, drängt der
    Prompt Whisper zum ähnlich klingenden „Einsatzleitung“."""
    if field == "an":
        namen = ", ".join(dict.fromkeys(funktionen))
        return TranscribeHint(field="an", prompt=f"Empfänger: {namen}.", hotwords=namen or None)
    if field == "inhalt":
        return TranscribeHint(field="inhalt", prompt=INHALT_PROMPT)
    return TranscribeHint(field=field)
