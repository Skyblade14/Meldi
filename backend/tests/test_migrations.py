"""Migrationen gegen eine Datenbank mit echten Daten – leere Datenbanken verdecken Fehler (Fremdschlüssel)."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.config import get_settings
from app.db import Base, get_engine, init_engine, new_session
from app.migrations import alembic_config
from app.models import AuditEvent

DATEN_0001 = [
    "INSERT INTO einsatz (id, bezeichnung, beginn, naechste_lfd_nr) VALUES (1, 'Alt', '2026-11-01 10:00:00', 2)",
    "INSERT INTO user (id, name, rolle, pin_hash, aktiv) VALUES (1, 'Melder 1', 'melder', 'x', 1)",
    "INSERT INTO anmeldung (id, user_id, einsatz_id, funktion, token_hash, angemeldet_at, gueltig_bis) "
    "VALUES (1, 1, 1, 'EA Brand', 'abc', '2026-11-01 10:00:00', '2026-11-02 10:00:00')",
    "INSERT INTO nachricht (id, einsatz_id, lfd_nr, von_funktion, von_user_id, anmeldung_id, an, inhalt, "
    "prioritaet, eingang_at, status, eingabe) VALUES (1, 1, 1, 'EA Brand', 1, 1, 'ELW', 'Feuer aus', 'blitz', "
    "'2026-11-01 10:05:00', 'neu', '{}')",
    "INSERT INTO audit_event (id, nachricht_id, user_id, funktion, aktion, zeitpunkt, aenderungen) "
    "VALUES (1, 1, 1, 'EA Brand', 'erstellt', '2026-11-01 10:05:00', '{}')",
]


@pytest.fixture
def db_0001(tmp_path, monkeypatch):
    monkeypatch.setenv("MELDI_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    init_engine()
    command.upgrade(alembic_config(), "0001")
    with get_engine().begin() as conn:
        for sql in DATEN_0001:
            conn.execute(text(sql))
    yield
    get_settings.cache_clear()


def spalten(tabelle: str) -> set[str]:
    with get_engine().connect() as conn:
        return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({tabelle})")}


def test_upgrade_und_downgrade_mit_daten(db_0001):
    command.upgrade(alembic_config(), "head")
    assert "prioritaet" not in spalten("nachricht")
    assert not {"rolle", "pin_hash", "aktiv"} & spalten("user")
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT inhalt FROM nachricht")).scalar_one() == "Feuer aus"
        assert conn.execute(text("SELECT count(*) FROM audit_event")).scalar_one() == 1
        assert conn.execute(text("SELECT rolle FROM anmeldung")).scalar_one() == "melder"
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1  # wieder aktiv
        tabellen = {r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any(t.startswith("_alembic_tmp") for t in tabellen)

    command.downgrade(alembic_config(), "0003")
    with get_engine().connect() as conn:
        assert conn.execute(text('SELECT rolle FROM "user"')).scalar_one() == "melder"

    command.downgrade(alembic_config(), "0001")
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT prioritaet FROM nachricht")).scalar_one() == "normal"


def test_modelle_und_migrationen_stimmen_ueberein(db_url):
    with get_engine().connect() as conn:
        kontext = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(kontext, Base.metadata) == []


@pytest.fixture
def audit_id(melder) -> int:
    melder.post("/api/messages", json={"an": "ELW", "inhalt": "Lage stabil"})
    with new_session() as db:
        return db.query(AuditEvent).one().id


@pytest.mark.parametrize(
    "sql", ["UPDATE audit_event SET funktion = 'gefaelscht' WHERE id = :id", "DELETE FROM audit_event WHERE id = :id"]
)
def test_audit_ist_append_only(audit_id, sql):
    with pytest.raises(DBAPIError, match="append-only"), get_engine().begin() as conn:
        conn.execute(text(sql), {"id": audit_id})
    with new_session() as db:
        assert db.get(AuditEvent, audit_id).funktion == "EA Brand"
