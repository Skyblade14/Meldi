from alembic import context
from sqlalchemy import Connection

import app.models  # noqa: F401  – registriert alle Tabellen
from app.db import Base, get_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=str(get_engine().url), target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def _migriere(connection: Connection) -> None:
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # Batch-Migrationen bauen Tabellen neu auf (Kopie, DROP, RENAME). Mit aktiven Fremdschlüsseln scheitert
        # das DROP, sobald andere Tabellen auf die Tabelle verweisen. Das PRAGMA wirkt nur außerhalb einer
        # Transaktion, daher vorher setzen und die Integrität am Ende selbst prüfen.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
    try:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
            if sqlite:
                verstoesse = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if verstoesse:
                    raise RuntimeError(f"Migration verletzt Fremdschlüssel: {verstoesse[:5]}")
    finally:
        if sqlite:
            connection.rollback()  # nichts offen lassen, sonst wirkt das PRAGMA nicht
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _migriere(connection)
        return
    with get_engine().connect() as connection:
        _migriere(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
