"""出来事の作品を外す

出来事は作品(章)に結ばず、見取り図は章の話の期間に重なる出来事をすべて出す。列を消すと、その外部キーとインデックスも消える。

Revision ID: 742356006819
Revises: e6effee9826b
Create Date: 2026-11-20 12:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '742356006819'
down_revision: Union[str, Sequence[str], None] = 'e6effee9826b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('event', 'story_id')


def downgrade() -> None:
    op.add_column('event', sa.Column(
        'story_id', sa.Integer(), nullable=True,
        comment='この出来事を筋に置く作品(章)。空なら、どの章にも置かない世界の出来事'))
    op.create_index('ix_event_story_id', 'event', ['story_id'], unique=False)
    op.create_foreign_key('event_story_id_fkey', 'event', 'story', ['story_id'], ['id'])
