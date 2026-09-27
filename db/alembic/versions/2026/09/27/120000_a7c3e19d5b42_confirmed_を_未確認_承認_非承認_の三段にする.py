"""confirmed を 未確認/承認/非承認 の三段にする

Revision ID: a7c3e19d5b42
Revises: f000f08fffa6
Create Date: 2026-09-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e19d5b42'
down_revision: Union[str, Sequence[str], None] = 'f000f08fffa6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("idea", "meme")


def upgrade() -> None:
    """bool の confirmed を文字列にし、true を 承認、false を 未確認 に読み替える。非承認はまだ無い。"""
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('confirmed', existing_type=sa.Boolean(), type_=sa.String(),
                                  existing_nullable=False)
        # 型を変えたあとの列には、元の 1/0 が '1'/'0' の文字で残る
        op.execute(f"UPDATE {table} SET confirmed = CASE WHEN confirmed IN ('1', 1, 'true') "
                   f"THEN '承認' ELSE '未確認' END")


def downgrade() -> None:
    """承認 だけを true に戻す。非承認は未確認と同じ false になる。"""
    for table in _TABLES:
        op.execute(f"UPDATE {table} SET confirmed = CASE WHEN confirmed = '承認' THEN 1 ELSE 0 END")
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('confirmed', existing_type=sa.String(), type_=sa.Boolean(),
                                  existing_nullable=False)
