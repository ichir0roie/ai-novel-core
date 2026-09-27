"""md の同期を廃止し directory_path filename を消す

Revision ID: c4d8f2a61e93
Revises: a7c3e19d5b42
Create Date: 2026-09-27 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d8f2a61e93'
down_revision: Union[str, Sequence[str], None] = 'a7c3e19d5b42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 本文を持つ(md に出していた)テーブル
_TABLES = ("location", "event", "meme", "oracle", "character", "character_relation", "idea", "story", "plot",
           "episode")


def upgrade() -> None:
    """md の置き場所の列を消す。oracle は md 名が題だったので、`title` に移してから消す。"""
    with op.batch_alter_table('oracle', schema=None) as batch_op:
        batch_op.add_column(sa.Column('title', sa.String(), nullable=True, comment='題。覚え書きを呼ぶ名前'))
    op.execute("UPDATE oracle SET title = CASE WHEN directory_path IS NULL OR directory_path = '' THEN filename "
               "ELSE directory_path || '/' || filename END WHERE filename IS NOT NULL")
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('filename')
            batch_op.drop_column('directory_path')


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('directory_path', sa.String(), nullable=True))
            batch_op.add_column(sa.Column('filename', sa.String(), nullable=True))
    op.execute("UPDATE oracle SET filename = title")
    with op.batch_alter_table('oracle', schema=None) as batch_op:
        batch_op.drop_column('title')
