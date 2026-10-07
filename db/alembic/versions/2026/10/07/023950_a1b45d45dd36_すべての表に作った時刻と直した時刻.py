"""すべての表に作った時刻と直した時刻

すべての表に `created_at`(作った時刻)と `updated_at`(直した時刻)を足す。どちらも既定値は `now()` で、
直した時刻は PostgreSQL の関数 `set_updated_at` を表ごとの BEFORE UPDATE のトリガーから呼んで入れ直す
(`db/postgres/timestamps.py`)。既にある行は、作った時刻が分からないので両方ともこのマイグレーションを当てた時刻になる。

Revision ID: a1b45d45dd36
Revises: 766455616c66
Create Date: 2026-10-07 02:39:50.731400

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.postgres.timestamps import FUNCTION, install_updated_at


# revision identifiers, used by Alembic.
revision: str = 'a1b45d45dd36'
down_revision: Union[str, Sequence[str], None] = '766455616c66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# このマイグレーションの時点の表(schema.py から読まない。あとで表が増えても、ここで触る表は変えない)
TABLES = (
    'character', 'character_history', 'character_history_knower', 'character_location', 'character_parameter',
    'character_relation', 'character_relation_history', 'character_skill', 'character_skill_history',
    'character_skill_history_knower', 'episode', 'episode_character', 'episode_character_session', 'event',
    'event_character', 'event_seed', 'event_summary', 'idea', 'idea_history', 'idea_history_knower', 'location',
    'location_history', 'location_history_knower', 'meme', 'oracle', 'personality_level', 'story', 'style_preference',
)


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES:
        op.add_column(table, sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                                       nullable=False, comment='行を作った時刻'))
        op.add_column(table, sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                                       nullable=False, comment='行を最後に直した時刻'))
    install_updated_at(op.get_bind(), TABLES)


def downgrade() -> None:
    """Downgrade schema."""
    for table in TABLES:
        op.execute(f'DROP TRIGGER IF EXISTS {FUNCTION} ON "{table}"')
        op.drop_column(table, 'updated_at')
        op.drop_column(table, 'created_at')
    op.execute(f'DROP FUNCTION IF EXISTS {FUNCTION}()')
