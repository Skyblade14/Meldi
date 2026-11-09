"""audit_event per Trigger gegen Ändern und Löschen sperren

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08 14:00:00.000000

Künftige Migrationen, die audit_event per batch_alter_table neu aufbauen, verlieren die Trigger (DROP TABLE) und
müssen sie wieder anlegen.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for name, ereignis in (("audit_event_kein_update", "UPDATE"), ("audit_event_kein_delete", "DELETE")):
        op.execute(
            f"CREATE TRIGGER {name} BEFORE {ereignis} ON audit_event "
            "BEGIN SELECT RAISE(ABORT, 'audit_event ist append-only'); END"
        )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_event_kein_update")
    op.execute("DROP TRIGGER IF EXISTS audit_event_kein_delete")
