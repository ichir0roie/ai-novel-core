"""話の概要の列を消す

話の流れは、登場人物の来歴と、語り部が読む直近の話の本文で受け継ぐ。AI が本文から作っていた概要(`summary_text`)と、
その元の本文のハッシュ(`summary_source_hash`)は使わなくなったので消す。残っていた概要も消える。

Revision ID: a42126849c99
Revises: 73a3d4b42185
Create Date: 2026-10-19 22:15:46.013114

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a42126849c99'
down_revision: Union[str, Sequence[str], None] = '73a3d4b42185'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('episode', 'summary_text')
    op.drop_column('episode', 'summary_source_hash')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('episode', sa.Column('summary_text', sa.VARCHAR(), autoincrement=False, nullable=True, comment='本文の概要。AI が本文から作る。まだ作っていなければ空'))
    op.add_column('episode', sa.Column('summary_source_hash', sa.VARCHAR(), autoincrement=False, nullable=True, comment='概要を作った本文の sha256。本文と食い違ったら概要を作り直す'))
