import enum
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, str_enum, utcnow


class Status(enum.StrEnum):
    NEU = "neu"
    GESICHTET = "gesichtet"
    ERLEDIGT = "erledigt"


class Eingabeart(enum.StrEnum):
    TEXT = "text"
    SPRACHE = "sprache"


class Nachricht(Base):
    """Eine Nachricht – digitales Gegenstück zum Vierfachvordruck."""

    __tablename__ = "nachricht"
    __table_args__ = (
        UniqueConstraint("einsatz_id", "lfd_nr"),
        UniqueConstraint("anmeldung_id", "sende_id", name="uq_nachricht_sende_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    einsatz_id: Mapped[int] = mapped_column(ForeignKey("einsatz.id"), index=True)
    lfd_nr: Mapped[int]

    # Wer
    von_funktion: Mapped[str] = mapped_column(String(80))
    von_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    anmeldung_id: Mapped[int] = mapped_column(ForeignKey("anmeldung.id"))
    # An wen
    an: Mapped[str] = mapped_column(String(120))
    an_funktion_id: Mapped[int | None] = mapped_column(ForeignKey("funktion.id"))
    # Was
    inhalt: Mapped[str] = mapped_column(Text)
    # Wann – eingang_at (Server) ist maßgeblich, erfasst_at (Handy-Uhr) nur informativ.
    erfasst_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    eingang_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    status: Mapped[Status] = mapped_column(str_enum(Status), default=Status.NEU)

    # Herkunft der Feldinhalte für spätere Auswertung der Spracherkennung:
    # {"an": {"art": "sprache", "rohtext": "...", "modell": "large-v3-turbo"}, "inhalt": {...}}
    eingabe: Mapped[dict] = mapped_column(JSON, default=dict)

    # Vom Handy je Formular erzeugt: Ein wiederholtes Absenden (Antwort verloren) legt keine zweite Nachricht an.
    sende_id: Mapped[str | None] = mapped_column(String(64))
    # Ordner in der Einsatzablage, relativ zu MELDI_ABLAGE_DIR. Gespeichert statt berechnet, damit er sich nie
    # ändert (Zeitzone, Bezeichnung).
    ablage_ordner: Mapped[str | None] = mapped_column(String(300))

    von_user = relationship("User", lazy="joined")
    einsatz = relationship("Einsatz", lazy="joined")
    anhaenge = relationship("Anhang", order_by="Anhang.id", lazy="selectin")
