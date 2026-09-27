"""検証結果の節を本文に統合し、fact_check列を削除する

Revision ID: 1d83860536f9
Revises: 7d92c2c626f3
Create Date: 2026-09-27 22:47:07.119271

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1d83860536f9'
down_revision: Union[str, Sequence[str], None] = '7d92c2c626f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FACT_CHECK_HEADING = "# 検証結果"


def _merge_fact_check_into_text(conn) -> None:
    """各テーブルの fact_check(検証結果)の値を、対応する行の text 末尾に節として書き足す。"""
    for table in ("idea", "meme", "oracle"):
        rows = conn.execute(sa.text(
            f"SELECT id, text, fact_check FROM {table} WHERE fact_check IS NOT NULL AND fact_check != ''"
        )).fetchall()
        for row in rows:
            base = (row.text or "").rstrip()
            merged = (f"{base}\n\n{_FACT_CHECK_HEADING}\n{row.fact_check}" if base
                      else f"{_FACT_CHECK_HEADING}\n{row.fact_check}")
            conn.execute(sa.text(f"UPDATE {table} SET text = :text WHERE id = :id"),
                         {"text": merged, "id": row.id})


def upgrade() -> None:
    """検証結果の節を本文に統合し、fact_check 列を削除する。"""
    _merge_fact_check_into_text(op.get_bind())

    with op.batch_alter_table('idea', schema=None) as batch_op:
        batch_op.drop_column('fact_check')

    with op.batch_alter_table('meme', schema=None) as batch_op:
        batch_op.drop_column('fact_check')

    with op.batch_alter_table('oracle', schema=None) as batch_op:
        batch_op.drop_column('fact_check')


def downgrade() -> None:
    """fact_check 列を戻す(本文に統合済みの検証結果はここでは分離しない。空のまま戻る)。"""
    with op.batch_alter_table('oracle', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fact_check', sa.VARCHAR(), nullable=True))

    with op.batch_alter_table('meme', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fact_check', sa.VARCHAR(), nullable=True))

    with op.batch_alter_table('idea', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fact_check', sa.VARCHAR(), nullable=True))
