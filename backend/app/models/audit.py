from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, utcnow


class AuditEvent(Base):
    """Append-only Protokoll aller Änderungen an Nachrichten. Wird nie verändert oder gelöscht."""

    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    nachricht_id: Mapped[int] = mapped_column(ForeignKey("nachricht.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    funktion: Mapped[str] = mapped_column(String(80))
    aktion: Mapped[str] = mapped_column(String(40))  # erstellt | geaendert | status
    zeitpunkt: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # {"feld": {"alt": ..., "neu": ...}}
    aenderungen: Mapped[dict] = mapped_column(JSON, default=dict)

    user = relationship("User", lazy="joined")
