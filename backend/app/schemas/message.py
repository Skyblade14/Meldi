from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models import Anhangart, Eingabeart, Status


class FeldEingabe(BaseModel):
    """Wie ein Feld befüllt wurde – für die Auswertung der Spracherkennung."""

    art: Eingabeart = Eingabeart.TEXT
    rohtext: str | None = Field(default=None, max_length=5000)  # unveränderte STT-Ausgabe
    modell: str | None = Field(default=None, max_length=100)


class NachrichtCreate(BaseModel):
    an: str = Field(min_length=1, max_length=120)
    inhalt: str = Field(min_length=1, max_length=5000)
    erfasst_at: AwareDatetime | None = None  # Handy-Uhr, nur informativ
    eingabe: dict[str, FeldEingabe] = Field(default_factory=dict, max_length=5)
    # IDs vorläufiger Uploads (Sprachaufnahmen aus /api/speech/transcribe, Fotos aus /api/uploads/foto)
    anhaenge: list[str] = Field(default_factory=list, max_length=40)
    # Je Formular vom Handy erzeugt; dieselbe ID zweimal ergibt keine zweite Nachricht.
    sende_id: str | None = Field(default=None, pattern=r"^[0-9A-Za-z-]{8,64}$")


class AnhangOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    art: Anhangart
    feld: str | None
    dateiname: str
    mime: str
    groesse: int
    meta: dict


class NachrichtOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lfd_nr: int
    von_funktion: str
    von_name: str
    an: str
    an_funktion_id: int | None
    inhalt: str
    status: Status
    erfasst_at: datetime | None
    eingang_at: datetime
    eingabe: dict
    anhaenge: list[AnhangOut] = []
    # Nur in der Antwort auf das Absenden: Anhänge, die nicht (mehr) auf dem Server lagen.
    fehlende_anhaenge: int = 0


class StatusUpdate(BaseModel):
    status: Status


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    aktion: str
    funktion: str
    name: str
    zeitpunkt: datetime
    aenderungen: dict
