"""人物のパラメータと来歴から end を消し、没年を character に持つ

パラメータ・来歴の行は、始まり(`start`)から先ずっと効き、後に始まる行が上書き・書き足す。
今まで一番後に始まるパラメータの行の end で表していた死亡は、character の `end`(没年)へ移す。
終わりのあった来歴の行は、説明の末尾に「(<年>年まで)」を足して残す。

Revision ID: cfbeb1b66a7b
Revises: 89d976cee24a
Create Date: 2026-10-01 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cfbeb1b66a7b'
down_revision: Union[str, Sequence[str], None] = '89d976cee24a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_character = sa.table("character", sa.column("id", sa.Integer), sa.column("end", sa.BigInteger))
_parameter = sa.table(
    "character_parameter",
    sa.column("id", sa.Integer), sa.column("character_id", sa.Integer),
    sa.column("start", sa.BigInteger), sa.column("end", sa.BigInteger))
_history = sa.table(
    "character_history",
    sa.column("id", sa.Integer), sa.column("end", sa.BigInteger), sa.column("description", sa.String))


def _last_rows(conn) -> dict[int, tuple[int, int | None]]:
    """人物ごとの、一番後に始まる行(始まりのある行が無ければ一番後に作った行)の (id, end)。"""
    rows = conn.execute(sa.select(_parameter.c.id, _parameter.c.character_id, _parameter.c.start, _parameter.c.end)
                        .order_by(_parameter.c.character_id, _parameter.c.id)).fetchall()
    by_character: dict[int, list[tuple[int, int | None, int | None]]] = {}
    for row_id, character_id, start, end in rows:
        by_character.setdefault(character_id, []).append((row_id, start, end))
    last = {}
    for character_id, items in by_character.items():
        bounded = [item for item in items if item[1] is not None]
        row_id, _, end = max(bounded, key=lambda item: item[1] or 0) if bounded else items[-1]
        last[character_id] = (row_id, end)
    return last


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('character', schema=None) as batch_op:
        batch_op.add_column(sa.Column('end', sa.BigInteger(), nullable=True,
                                      comment='没年(この時からはいない)。空なら死んでいない'))

    conn = op.get_bind()
    for character_id, (_, end) in _last_rows(conn).items():
        if end is not None:
            conn.execute(sa.update(_character).where(_character.c.id == character_id).values(end=end))

    ended = conn.execute(sa.select(_history.c.id, _history.c.end, _history.c.description)
                         .where(_history.c.end.is_not(None))).fetchall()
    for history_id, end, description in ended:
        # 台帳の時刻の整数は 年*10^10 + 月*10^8 + …(db/stamp.py)
        conn.execute(sa.update(_history).where(_history.c.id == history_id)
                     .values(description=f"{description}({end // 10 ** 10}年まで)"))

    with op.batch_alter_table('character_parameter', schema=None) as batch_op:
        batch_op.drop_column('end')
    with op.batch_alter_table('character_history', schema=None) as batch_op:
        batch_op.drop_column('end')
        batch_op.alter_column('start', existing_type=sa.BigInteger(), existing_nullable=True,
                              comment='この説明・来歴が効き始める時(起きた時)。空なら始まりを限らない')
        batch_op.alter_column('description', existing_type=sa.String(), existing_nullable=False,
                              comment='説明・来歴')


def downgrade() -> None:
    """Downgrade schema.

    没年は一番後に始まるパラメータの行の end へ戻す。来歴の説明に足した「(<年>年まで)」は戻さない。
    """
    with op.batch_alter_table('character_history', schema=None) as batch_op:
        batch_op.alter_column('start', existing_type=sa.BigInteger(), existing_nullable=True,
                              comment='この説明が効き始める時。空なら始まりを限らない')
        batch_op.alter_column('description', existing_type=sa.String(), existing_nullable=False,
                              comment='この期間での説明')
        batch_op.add_column(sa.Column(
            'end', sa.BigInteger(), nullable=True,
            comment='この説明が効き終わる時(この時からは効かない)。空なら終わりを限らない'))
    with op.batch_alter_table('character_parameter', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'end', sa.BigInteger(), nullable=True,
            comment='この値が効き終わる時(この時からは効かない)。空なら終わりまで'))

    conn = op.get_bind()
    died = dict(conn.execute(sa.select(_character.c.id, _character.c.end).where(_character.c.end.is_not(None))).fetchall())
    for character_id, (row_id, _) in _last_rows(conn).items():
        if character_id in died:
            conn.execute(sa.update(_parameter).where(_parameter.c.id == row_id).values(end=died[character_id]))

    with op.batch_alter_table('character', schema=None) as batch_op:
        batch_op.drop_column('end')
