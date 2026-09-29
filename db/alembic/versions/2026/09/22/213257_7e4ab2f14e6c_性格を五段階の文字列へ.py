"""性格を五段階の文字列へ

Revision ID: 7e4ab2f14e6c
Revises: 
Create Date: 2026-09-22 21:32:57.628561

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.schema import PERSONALITY_COLUMNS

# この版のときの既定(並)。後で schema から消えたので、値で持つ
PERSONALITY_DEFAULT = "並"


# revision identifiers, used by Alembic.
revision: str = '7e4ab2f14e6c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 旧 db に整数(-5〜5)で入っている値は、大きさで五段階へ寄せてから型を変える。
    for column in PERSONALITY_COLUMNS:
        op.execute(
            f'UPDATE character SET "{column}" = CASE '
            f'WHEN CAST("{column}" AS INTEGER) <= -4 THEN \'無\' '
            f'WHEN CAST("{column}" AS INTEGER) < 0 THEN \'低\' '
            f'WHEN CAST("{column}" AS INTEGER) >= 4 THEN \'必\' '
            f'WHEN CAST("{column}" AS INTEGER) > 0 THEN \'高\' '
            f'ELSE \'並\' END'
        )
    with op.batch_alter_table('character') as batch_op:
        for column in PERSONALITY_COLUMNS:
            batch_op.alter_column(
                column, existing_type=sa.Integer(), type_=sa.String(),
                existing_nullable=False, server_default=PERSONALITY_DEFAULT)


def downgrade() -> None:
    """Downgrade schema."""
    for column in PERSONALITY_COLUMNS:
        op.execute(
            f'UPDATE character SET "{column}" = CASE "{column}" '
            f"WHEN '無' THEN -5 WHEN '低' THEN -2 WHEN '高' THEN 2 WHEN '必' THEN 5 ELSE 0 END"
        )
    with op.batch_alter_table('character') as batch_op:
        for column in PERSONALITY_COLUMNS:
            batch_op.alter_column(
                column, existing_type=sa.String(), type_=sa.Integer(),
                existing_nullable=False, server_default=None)
