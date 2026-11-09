"""Anmeldung ohne PIN: Rolle wandert vom User zur Anmeldung

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLLE = sa.Enum('melder', 'elw', 'beobachter', name='rolle', native_enum=False, length=20)


def upgrade() -> None:
    with op.batch_alter_table('anmeldung', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rolle', ROLLE, nullable=True))
    op.execute('UPDATE anmeldung SET rolle = (SELECT rolle FROM "user" WHERE "user".id = anmeldung.user_id)')
    with op.batch_alter_table('anmeldung', schema=None) as batch_op:
        batch_op.alter_column('rolle', existing_type=ROLLE, nullable=False)

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('aktiv')
        batch_op.drop_column('pin_hash')
        batch_op.drop_column('rolle')


def downgrade() -> None:
    # Die PINs sind verloren: Nach einem Downgrade kann sich niemand anmelden, bis sie neu gesetzt wurden.
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rolle', ROLLE, nullable=False, server_default='melder'))
        batch_op.add_column(sa.Column('pin_hash', sa.String(length=200), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('aktiv', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute(
        'UPDATE "user" SET rolle = COALESCE((SELECT a.rolle FROM anmeldung a WHERE a.user_id = "user".id '
        "ORDER BY a.id DESC LIMIT 1), 'melder')"
    )
    with op.batch_alter_table('anmeldung', schema=None) as batch_op:
        batch_op.drop_column('rolle')
