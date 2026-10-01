"""人物の来歴の始まりを年の整数にし、同じ年の行をまとめる

来歴の行を増やしすぎないよう、`character_history.start` を時刻(Stamp)から年の整数に変え、
同じ人物・同じ年の行は説明を改行でつないだ一行にまとめる。

Revision ID: cf6fabb7bc02
Revises: cfbeb1b66a7b
Create Date: 2026-10-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.stamp import Stamp


# revision identifiers, used by Alembic.
revision: str = 'cf6fabb7bc02'
down_revision: Union[str, Sequence[str], None] = 'cfbeb1b66a7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_history = sa.table(
    "character_history",
    sa.column("id", sa.Integer), sa.column("character_id", sa.Integer),
    sa.column("start", sa.BigInteger), sa.column("description", sa.String))


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    rows = conn.execute(
        sa.select(_history.c.id, _history.c.character_id, _history.c.start, _history.c.description)
        .where(_history.c.start.is_not(None))
        .order_by(_history.c.character_id, _history.c.start, _history.c.id)).fetchall()
    kept: dict[tuple[int, int], tuple[int, list[str]]] = {}
    merged: list[int] = []
    for history_id, character_id, start, description in rows:
        # 台帳の時刻の整数は 年*10^10 + 月*10^8 + …(db/stamp.py)
        key = (character_id, start // 10 ** 10)
        if key in kept:
            kept[key][1].append(description)
            merged.append(history_id)
        else:
            kept[key] = (history_id, [description])
    for (_, year), (history_id, descriptions) in kept.items():
        conn.execute(sa.update(_history).where(_history.c.id == history_id)
                     .values(start=year, description="\n".join(descriptions)))
    if merged:
        conn.execute(sa.delete(_history).where(_history.c.id.in_(merged)))

    with op.batch_alter_table('character_history', schema=None) as batch_op:
        batch_op.alter_column('start', existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=True,
                              comment='この説明・来歴が効き始める年(起きた年)。空なら始まりを限らない')


def downgrade() -> None:
    """Downgrade schema. まとめた行は分け直さない。"""
    with op.batch_alter_table('character_history', schema=None) as batch_op:
        batch_op.alter_column('start', existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True,
                              comment='この説明・来歴が効き始める時(起きた時)。空なら始まりを限らない')

    conn = op.get_bind()
    rows = conn.execute(sa.select(_history.c.id, _history.c.start).where(_history.c.start.is_not(None))).fetchall()
    for history_id, year in rows:
        conn.execute(sa.update(_history).where(_history.c.id == history_id).values(start=Stamp(year).to_int()))
