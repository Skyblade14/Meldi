import enum
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, str_enum, utcnow


class Rolle(enum.StrEnum):
    MELDER = "melder"
    ELW = "elw"
    BEOBACHTER = "beobachter"  # liest mit (z.B. Einsatzleiter am Handy), erfasst und ändert nichts


class User(Base):
    """Eine Person, nur über den selbst angegebenen Namen bekannt (keine Passwörter, siehe Roadmap)."""

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Anmeldung(Base):
    """Eine Anmeldung eines Users in einer Funktion während eines Einsatzes (= Session)."""

    __tablename__ = "anmeldung"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    einsatz_id: Mapped[int] = mapped_column(ForeignKey("einsatz.id"))
    # Gehört zur Anmeldung: Dieselbe Person kann als Melder und im ELW arbeiten.
    rolle: Mapped[Rolle] = mapped_column(str_enum(Rolle))
    funktion: Mapped[str] = mapped_column(String(80))
    # SHA-256 des Session-Tokens; das Token selbst liegt nur im Cookie.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    angemeldet_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    gueltig_bis: Mapped[datetime] = mapped_column(UTCDateTime)
    abgemeldet_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship(lazy="joined")
    einsatz = relationship("Einsatz", lazy="joined")
