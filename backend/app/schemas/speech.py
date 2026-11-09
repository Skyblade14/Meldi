from pydantic import BaseModel


class FunktionVorschlag(BaseModel):
    funktion_id: int
    name: str
    score: float


class TranscribeOut(BaseModel):
    text: str
    rohtext: str
    modell: str
    audio_sekunden: float
    verarbeitung_sekunden: float
    warte_sekunden: float
    # Nur für Feld „an": bekannte Funktionen, die zum Gesprochenen passen (bestes zuerst).
    vorschlaege: list[FunktionVorschlag] = []
    # Vorläufig abgelegte Aufnahme; beim Absenden in `anhaenge` mitschicken.
    aufnahme_id: str | None = None


class SttStatus(BaseModel):
    aktiv: bool
    bereit: bool
    modell: str | None
    warteschlange: int
