"""人物の芯を character.text に戻し、来歴の始まりの無い行を年未定にする

人物の芯(説明・meme・行動原理・plot)は `character.text` に持ち、`character_history` は年ごとの来歴だけにする。
来歴の始まりの無い行(芯)を人物ごとに `text` へ移して消す。以後、始まりの無い来歴の行は、年がまだ決まっていない構想として
話・出来事には渡さない。

Revision ID: e7f2aa3d09df
Revises: cf6fabb7bc02
Create Date: 2026-10-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f2aa3d09df'
down_revision: Union[str, Sequence[str], None] = 'cf6fabb7bc02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_character = sa.table("character", sa.column("id", sa.Integer), sa.column("text", sa.String))
_history = sa.table(
    "character_history",
    sa.column("id", sa.Integer), sa.column("character_id", sa.Integer),
    sa.column("start", sa.Integer), sa.column("description", sa.String))


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('character', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'text', sa.String(), nullable=True,
            comment='人物の芯(説明・meme・行動原理・plot)。いつの話・出来事にも渡す'))

    conn = op.get_bind()
    rows = conn.execute(
        sa.select(_history.c.id, _history.c.character_id, _history.c.description)
        .where(_history.c.start.is_(None))
        .order_by(_history.c.character_id, _history.c.id)).fetchall()
    cores: dict[int, list[str]] = {}
    for _, character_id, description in rows:
        cores.setdefault(character_id, []).append(description)
    for character_id, descriptions in cores.items():
        conn.execute(sa.update(_character).where(_character.c.id == character_id)
                     .values(text="\n\n".join(descriptions)))
    if rows:
        conn.execute(sa.delete(_history).where(_history.c.id.in_([row[0] for row in rows])))

    with op.batch_alter_table('character_history', schema=None) as batch_op:
        batch_op.alter_column('start', existing_type=sa.Integer(), existing_nullable=True,
                              comment='起きた年(この来歴が効き始める年)。空なら年が決まっていない(話・出来事には渡さない)')
        batch_op.alter_column('description', existing_type=sa.String(), existing_nullable=False, comment='来歴')


def downgrade() -> None:
    """戻さない。"""
    raise NotImplementedError("人物の芯を character.text に戻したあとは、前の版へ戻さない")
