from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, utcnow


class Einsatz(Base):
    __tablename__ = "einsatz"

    id: Mapped[int] = mapped_column(primary_key=True)
    bezeichnung: Mapped[str] = mapped_column(String(200))
    beginn: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    ende: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Zähler für die laufende Nachrichtennummer; wird atomar per UPDATE … RETURNING hochgezählt.
    naechste_lfd_nr: Mapped[int] = mapped_column(default=1)
    # Ordnername in der Einsatzablage, wird bei der ersten Nachricht festgelegt.
    ablage_ordner: Mapped[str | None] = mapped_column(String(200))

    funktionen: Mapped[list["Funktion"]] = relationship(
        back_populates="einsatz", order_by="Funktion.sortierung", cascade="all, delete-orphan"
    )


class Funktion(Base):
    """Eine Funktion/Stelle im Einsatz (z.B. „EA Brand"). Dient als Absender, Empfänger und STT-Vokabular."""

    __tablename__ = "funktion"
    __table_args__ = (UniqueConstraint("einsatz_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    einsatz_id: Mapped[int] = mapped_column(ForeignKey("einsatz.id"))
    name: Mapped[str] = mapped_column(String(80))
    # Kommagetrennte gesprochene Varianten, z.B. „Einsatzabschnitt Brand, Abschnitt Brand".
    aliase: Mapped[str] = mapped_column(String(500), default="")
    sortierung: Mapped[int] = mapped_column(default=0)

    einsatz: Mapped[Einsatz] = relationship(back_populates="funktionen")

    @property
    def alias_liste(self) -> list[str]:
        return [a.strip() for a in self.aliase.split(",") if a.strip()]
