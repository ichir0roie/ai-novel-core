"""話の種を plot_text に、本文を main_text に改名し、要約を話の行へ統合する

Revision ID: 68d73c9feb64
Revises: 7a0189375695
Create Date: 2026-09-30 08:56:43.542826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68d73c9feb64'
down_revision: Union[str, Sequence[str], None] = '7a0189375695'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_summary_table() -> None:
    op.create_table(
        'episode_summary',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('episode_id', sa.Integer(), nullable=False),
        sa.Column('source_hash', sa.String(), nullable=False),
        sa.Column('summary', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['episode_id'], ['episode.id']),
        sa.ForeignKeyConstraint(['story_id'], ['story.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_episode_summary_episode_id', 'episode_summary', ['episode_id'], unique=True)
    op.create_index('ix_episode_summary_story_id', 'episode_summary', ['story_id'])


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.alter_column('key', new_column_name='plot_text', existing_type=sa.String(),
                              existing_nullable=False, existing_server_default=sa.text("('')"))
        batch_op.alter_column('text', new_column_name='main_text', existing_type=sa.String(),
                              existing_nullable=False, existing_server_default=sa.text("('')"))
        batch_op.add_column(sa.Column('summary_text', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('summary_source_hash', sa.String(), nullable=True))

    op.execute(
        "UPDATE episode SET "
        "summary_text = (SELECT summary FROM episode_summary WHERE episode_summary.episode_id = episode.id), "
        "summary_source_hash = (SELECT source_hash FROM episode_summary WHERE episode_summary.episode_id = episode.id)")
    op.drop_index('ix_episode_summary_story_id', table_name='episode_summary')
    op.drop_index('ix_episode_summary_episode_id', table_name='episode_summary')
    op.drop_table('episode_summary')


def downgrade() -> None:
    """Downgrade schema."""
    _create_summary_table()
    op.execute(
        "INSERT INTO episode_summary (story_id, episode_id, source_hash, summary) "
        "SELECT story_id, id, summary_source_hash, summary_text FROM episode "
        "WHERE summary_text IS NOT NULL AND summary_source_hash IS NOT NULL")

    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.drop_column('summary_source_hash')
        batch_op.drop_column('summary_text')
        batch_op.alter_column('main_text', new_column_name='text', existing_type=sa.String(),
                              existing_nullable=False, existing_server_default=sa.text("('')"))
        batch_op.alter_column('plot_text', new_column_name='key', existing_type=sa.String(),
                              existing_nullable=False, existing_server_default=sa.text("('')"))
