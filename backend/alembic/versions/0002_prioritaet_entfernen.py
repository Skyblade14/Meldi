"""Priorität entfernen

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07 20:00:00

Die Priorität ist aus dem Formular entfallen. Bereits erfasste Werte bleiben im Audit-Protokoll erhalten.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('nachricht', schema=None) as batch_op:
        batch_op.drop_column('prioritaet')


def downgrade() -> None:
    with op.batch_alter_table('nachricht', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'prioritaet',
            sa.Enum('normal', 'dringend', 'blitz', name='prioritaet', native_enum=False, length=20),
            nullable=False,
            server_default='normal',
        ))
