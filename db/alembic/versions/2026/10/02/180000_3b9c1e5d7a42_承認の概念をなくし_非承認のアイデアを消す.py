"""承認の概念をなくし、非承認のアイデアを消す

人物・出来事・アイデア・ミームの `confirmed`(未確認/承認/非承認)を消す。生んだものは足したその時から世界に出る。
退けた(非承認の)アイデアは、結んだ本文(出来事・話・人物)と呼び名ごと消す。下位のアイデアは、消すアイデアの上位へ繋ぎ直す。

Revision ID: 3b9c1e5d7a42
Revises: e7f2aa3d09df
Create Date: 2026-10-02 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b9c1e5d7a42'
down_revision: Union[str, Sequence[str], None] = 'e7f2aa3d09df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("character", "event", "idea", "meme")
_IDEA_LINKS = ("event_idea", "episode_idea", "character_idea", "idea_recognition")

_idea = sa.table("idea", sa.column("id", sa.Integer), sa.column("parent_idea_id", sa.Integer),
                 sa.column("confirmed", sa.String))


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    rejected = conn.execute(
        sa.select(_idea.c.id, _idea.c.parent_idea_id).where(_idea.c.confirmed == "非承認")
        .order_by(_idea.c.id)).fetchall()
    rejected_ids = {row[0] for row in rejected}
    parents = {row[0]: row[1] for row in rejected}

    def kept_parent(idea_id: int | None) -> int | None:
        # 上位も消すアイデアなら、さらに上へたどる
        while idea_id in rejected_ids:
            idea_id = parents[idea_id]
        return idea_id

    for idea_id, parent_id in rejected:
        conn.execute(sa.update(_idea).where(_idea.c.parent_idea_id == idea_id)
                     .values(parent_idea_id=kept_parent(parent_id)))
    if rejected_ids:
        for name in _IDEA_LINKS:
            link = sa.table(name, sa.column("idea_id", sa.Integer))
            conn.execute(sa.delete(link).where(link.c.idea_id.in_(rejected_ids)))
        conn.execute(sa.delete(_idea).where(_idea.c.id.in_(rejected_ids)))

    for name in _TABLES:
        with op.batch_alter_table(name, schema=None) as batch_op:
            batch_op.drop_column('confirmed')


def downgrade() -> None:
    """列だけを戻す(どの行も承認で始める)。消した非承認のアイデアは戻らない。"""
    for name in _TABLES:
        with op.batch_alter_table(name, schema=None) as batch_op:
            batch_op.add_column(sa.Column('confirmed', sa.String(), nullable=False, server_default='承認'))
        with op.batch_alter_table(name, schema=None) as batch_op:
            batch_op.alter_column('confirmed', server_default=None)
