"""話とアイデアの中間テーブル episode_idea を消す

Revision ID: 8f3a6d2c41b7
Revises: 1362ea2be0c5
Create Date: 2026-10-04 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f3a6d2c41b7'
down_revision: Union[str, Sequence[str], None] = '1362ea2be0c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('episode_idea', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_episode_idea_idea_id'))
        batch_op.drop_index(batch_op.f('ix_episode_idea_episode_id'))

    op.drop_table('episode_idea')


def downgrade() -> None:
    """Downgrade schema."""
    # 結んであった行は戻らない
    op.create_table('episode_idea',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('episode_id', sa.Integer(), nullable=False),
    sa.Column('idea_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['episode_id'], ['episode.id'], ),
    sa.ForeignKeyConstraint(['idea_id'], ['idea.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('episode_id', 'idea_id')
    )
    with op.batch_alter_table('episode_idea', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_episode_idea_episode_id'), ['episode_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_episode_idea_idea_id'), ['idea_id'], unique=False)
