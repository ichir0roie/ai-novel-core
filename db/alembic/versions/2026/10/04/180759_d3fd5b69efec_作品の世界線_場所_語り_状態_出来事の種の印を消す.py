"""作品の世界線_場所_語り_状態_出来事の種の印を消す

Revision ID: d3fd5b69efec
Revises: 96d918e7b476
Create Date: 2026-10-04 18:07:59.186462

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3fd5b69efec'
down_revision: Union[str, Sequence[str], None] = '96d918e7b476'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f('story_world_id_fkey'), 'story', type_='foreignkey')
    op.drop_constraint(op.f('story_location_id_fkey'), 'story', type_='foreignkey')
    op.drop_column('story', 'location_id')
    op.drop_column('story', 'narration')
    op.drop_column('story', 'state')
    op.drop_column('story', 'world_id')
    op.drop_column('story', 'event_seeded')


def downgrade() -> None:
    """Downgrade schema."""
    # 消した値は戻らない。NOT NULL の列は、残っている行を空(種は抜き出し済み)で埋めて戻す
    op.add_column('story', sa.Column('event_seeded', sa.BOOLEAN(), autoincrement=False, nullable=False,
                                     server_default=sa.true(),
                                     comment='出来事の種を抜き出し済みか。false に戻すと、次の毎日のルーチンで抜き出し直す'))
    op.add_column('story', sa.Column('world_id', sa.INTEGER(), autoincrement=False, nullable=True, comment='使用する世界線'))
    op.add_column('story', sa.Column('state', sa.VARCHAR(), autoincrement=False, nullable=False, server_default='',
                                     comment='状態'))
    op.add_column('story', sa.Column('narration', sa.VARCHAR(), autoincrement=False, nullable=False, server_default='',
                                     comment='語り'))
    op.add_column('story', sa.Column('location_id', sa.INTEGER(), autoincrement=False, nullable=True,
                                     comment='立つ場所。断面を取るのに使う'))
    for column in ('event_seeded', 'state', 'narration'):
        op.alter_column('story', column, server_default=None)
    op.create_foreign_key(op.f('story_location_id_fkey'), 'story', 'location', ['location_id'], ['id'])
    op.create_foreign_key(op.f('story_world_id_fkey'), 'story', 'location', ['world_id'], ['id'])
