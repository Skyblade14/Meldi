import enum
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, str_enum, utcnow


class Anhangart(enum.StrEnum):
    AUDIO = "audio"
    FOTO = "foto"


class Anhang(Base):
    """Datei zu einer Nachricht (Sprachaufnahme, Foto). Die Datei selbst liegt in der Einsatzablage."""

    __tablename__ = "anhang"

    id: Mapped[int] = mapped_column(primary_key=True)
    nachricht_id: Mapped[int] = mapped_column(ForeignKey("nachricht.id"), index=True)
    art: Mapped[Anhangart] = mapped_column(str_enum(Anhangart))
    feld: Mapped[str | None] = mapped_column(String(20))  # bei Audio: „an“ oder „inhalt“
    # Dateiname im Ordner der Nachricht, z.B. „inhalt_2.webm“
    dateiname: Mapped[str] = mapped_column(String(100))
    mime: Mapped[str] = mapped_column(String(100))
    groesse: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    hochgeladen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Audio: Rohtext, Text, Modell, Dauer. Foto: GPS, Aufnahmezeit, Abmessungen.
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
