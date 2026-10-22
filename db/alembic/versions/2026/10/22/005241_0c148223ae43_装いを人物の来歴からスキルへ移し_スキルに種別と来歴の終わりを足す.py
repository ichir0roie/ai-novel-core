"""装いを人物の来歴からスキルへ移し スキルに種別と来歴の終わりを足す

装いを、身に着けている物ごとのスキル(種別「装い」)で持ち、物の移り変わり(着けた・傷んだ・手放した)をスキルの来歴の行で
持てるようにする。スキルに種別(`kind`)を、スキルの来歴に終わり(`end`。この時刻からは効かない)を足す。

- 人物の来歴のうち種別「装い」の行は、一行ずつ、同じ人物の装いのスキル一つに移す。スキルの名前は行の文、本質は空にし、
  行の始まり・終わり・文と知る相手は、そのスキルの来歴の一行に写す。移した来歴の行と、その知る相手の行は消す

Revision ID: 0c148223ae43
Revises: 2b73cdce17d0
Create Date: 2026-10-22 00:52:41.648672

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c148223ae43'
down_revision: Union[str, Sequence[str], None] = '2b73cdce17d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OUTFIT_KIND = "装い"


def _knower_columns() -> tuple:
    # 列のオブジェクトは一つの表にしか付けられないので、表ごとに作る
    return (sa.column("id", sa.Integer), sa.column("knower_id", sa.Integer),
            sa.column("location_id", sa.Integer), sa.column("start", sa.BigInteger))


_history = sa.table(
    "character_history", sa.column("id", sa.Integer), sa.column("character_id", sa.Integer),
    sa.column("start", sa.BigInteger), sa.column("end", sa.BigInteger), sa.column("kind", sa.String),
    sa.column("description", sa.String))
_history_knower = sa.table("character_history_knower", sa.column("character_history_id", sa.Integer), *_knower_columns())
_skill = sa.table(
    "character_skill", sa.column("id", sa.Integer), sa.column("character_id", sa.Integer), sa.column("name", sa.String),
    sa.column("kind", sa.String), sa.column("text", sa.String))
_skill_history = sa.table(
    "character_skill_history", sa.column("id", sa.Integer), sa.column("character_skill_id", sa.Integer),
    sa.column("start", sa.BigInteger), sa.column("end", sa.BigInteger), sa.column("description", sa.String))
_skill_history_knower = sa.table(
    "character_skill_history_knower", sa.column("character_skill_history_id", sa.Integer), *_knower_columns())


def _knowers(conn, table, column, row_id: int) -> list[dict]:
    return [{"knower_id": knower.knower_id, "location_id": knower.location_id, "start": knower.start}
            for knower in conn.execute(sa.select(table).where(table.c[column] == row_id).order_by(table.c.id))]


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('character_history', 'kind',
               existing_type=sa.VARCHAR(),
               comment='種別(持ち物・記憶・隠し事など)。空なら起きた出来事',
               existing_comment='種別(装い・持ち物・記憶・隠し事など)。空なら起きた出来事',
               existing_nullable=True)
    op.add_column('character_skill', sa.Column('kind', sa.String(), nullable=True, comment='種別。「装い」なら身に着けている物で、見た人に知れる。空なら技・術・技能'))
    op.add_column('character_skill_history', sa.Column('end', sa.BigInteger(), nullable=True, comment='効き終わる時刻(この時刻からは効かない)。空なら終わりを限らない'))

    conn = op.get_bind()
    for row in conn.execute(sa.select(_history).where(_history.c.kind == OUTFIT_KIND).order_by(_history.c.id)).fetchall():
        skill_id = conn.execute(sa.insert(_skill).values(
            character_id=row.character_id, name=row.description, kind=OUTFIT_KIND, text="").returning(_skill.c.id)).scalar_one()
        history_id = conn.execute(sa.insert(_skill_history).values(
            character_skill_id=skill_id, start=row.start, end=row.end, description=row.description,
        ).returning(_skill_history.c.id)).scalar_one()
        knowers = _knowers(conn, _history_knower, "character_history_id", row.id)
        if knowers:
            conn.execute(sa.insert(_skill_history_knower), [{**knower, "character_skill_history_id": history_id}
                                                             for knower in knowers])
        conn.execute(sa.delete(_history_knower).where(_history_knower.c.character_history_id == row.id))
        conn.execute(sa.delete(_history).where(_history.c.id == row.id))


def downgrade() -> None:
    """Downgrade schema.

    装いのスキルの来歴の行を、種別「装い」の人物の来歴の行に戻し、装いのスキルを消してから、種別と終わりの列を消す。
    """
    conn = op.get_bind()
    for skill in conn.execute(sa.select(_skill).where(_skill.c.kind == OUTFIT_KIND).order_by(_skill.c.id)).fetchall():
        for row in conn.execute(sa.select(_skill_history).where(_skill_history.c.character_skill_id == skill.id)
                                .order_by(_skill_history.c.id)).fetchall():
            history_id = conn.execute(sa.insert(_history).values(
                character_id=skill.character_id, start=row.start, end=row.end, kind=OUTFIT_KIND,
                description=row.description).returning(_history.c.id)).scalar_one()
            knowers = _knowers(conn, _skill_history_knower, "character_skill_history_id", row.id)
            if knowers:
                conn.execute(sa.insert(_history_knower), [{**knower, "character_history_id": history_id}
                                                          for knower in knowers])
            conn.execute(sa.delete(_skill_history_knower).where(_skill_history_knower.c.character_skill_history_id == row.id))
        conn.execute(sa.delete(_skill_history).where(_skill_history.c.character_skill_id == skill.id))
        conn.execute(sa.delete(_skill).where(_skill.c.id == skill.id))

    op.drop_column('character_skill_history', 'end')
    op.drop_column('character_skill', 'kind')
    op.alter_column('character_history', 'kind',
               existing_type=sa.VARCHAR(),
               comment='種別(装い・持ち物・記憶・隠し事など)。空なら起きた出来事',
               existing_comment='種別(持ち物・記憶・隠し事など)。空なら起きた出来事',
               existing_nullable=True)
