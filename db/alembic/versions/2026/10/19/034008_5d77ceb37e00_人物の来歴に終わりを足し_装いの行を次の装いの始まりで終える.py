"""人物の来歴に終わりを足し、装いの行を次の装いの始まりで終える

装いを身に着けている物ごとの行で持ち、外した・失った時刻で終われるように、人物の来歴(`character_history`)に
終わり(`end`。この時刻からは効かない)を足す。その時刻に効いている装いの行をすべて重ねたものが見た目になる。

- これまでの装いの行は、その時刻の身なりをまるごと一文にした行で、一番新しい行だけが効いていた。見た目を変えないよう、
  人物ごとに始まりの決まった装いの行を古い順に並べ、次に始まる装いの行の始まりをその行の終わりにする
- 始まりの同じ装いの行が幾つもあれば、id の一番大きい行のほかは、その始まりで終える(効かない行になる)
- 始まりの空な行(時期の決まっていない構想)は話・出来事に渡らないので、終わりを入れない

Revision ID: 5d77ceb37e00
Revises: 4e0b659755e4
Create Date: 2026-10-19 03:40:08.739503

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d77ceb37e00'
down_revision: Union[str, Sequence[str], None] = '4e0b659755e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OUTFIT_KIND = "装い"

_history = sa.table(
    "character_history", sa.column("id", sa.Integer), sa.column("character_id", sa.Integer),
    sa.column("start", sa.BigInteger), sa.column("end", sa.BigInteger), sa.column("kind", sa.String))


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('character_history', sa.Column('end', sa.BigInteger(), nullable=True, comment='効き終わる時刻(この時刻からは効かない)。空なら終わりを限らない'))

    conn = op.get_bind()
    by_character: dict[int, list] = {}
    for row in conn.execute(
            sa.select(_history.c.id, _history.c.character_id, _history.c.start)
            .where(_history.c.kind == OUTFIT_KIND, _history.c.start.is_not(None))
            .order_by(_history.c.start, _history.c.id)).fetchall():
        by_character.setdefault(row.character_id, []).append(row)
    for rows in by_character.values():
        for row, following in zip(rows, rows[1:]):
            conn.execute(sa.update(_history).where(_history.c.id == row.id).values(end=following.start))


def downgrade() -> None:
    """Downgrade schema.

    終わりを消す。装いの行は残るので、身に着けている物ごとに分けた行のうち一番新しい行だけが見た目になる。
    """
    op.drop_column('character_history', 'end')
