"""Datenbank-Engine und Session-Handling (SQLite im WAL-Modus)."""

import enum
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import DateTime, Engine, Enum, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class UTCDateTime(TypeDecorator[datetime]):
    """Speichert Zeitpunkte als UTC und liefert sie immer zeitzonenbehaftet zurück."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Zeitpunkte müssen zeitzonenbehaftet sein")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


def str_enum(enum_cls: type[enum.StrEnum]) -> Enum:
    """Enum-Spalte, die den Wert („melder") statt des Namens („MELDER") speichert."""
    return Enum(enum_cls, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e])


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(url, connect_args={"check_same_thread": False} if is_sqlite else {})
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

    return engine


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_engine(url: str | None = None) -> Engine:
    global _engine, _session_factory
    settings = get_settings()
    if url is None:
        settings.lokal_dir.mkdir(parents=True, exist_ok=True)
        url = settings.db_url
    _engine = make_engine(url)
    _session_factory = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    return _engine or init_engine()


def new_session() -> Session:
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory()


def get_db() -> Iterator[Session]:
    with new_session() as session:
        yield session
