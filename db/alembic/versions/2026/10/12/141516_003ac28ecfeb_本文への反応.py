"""本文への反応

ユーザが書く本文を保存するたびの差分(`episode_comment_diff`)と、それを読んだ語り部・人物役の反応
(`episode_comment_reaction`)の表を足す。

Revision ID: 003ac28ecfeb
Revises: c634c557b443
Create Date: 2026-10-12 14:15:16.854232

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003ac28ecfeb'
down_revision: Union[str, Sequence[str], None] = 'c634c557b443'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('episode_comment_diff',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('episode_id', sa.Integer(), nullable=False),
    sa.Column('diff_text', sa.String(), nullable=False, comment='前に保存した本文からの差分(unified diff の形。前後の数行を添える)。終わりの合図の行では空'),
    sa.Column('closing', sa.Boolean(), nullable=False, comment='書き終えた合図。語り部と人物役はこの行を読んだら止まる'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を作った時刻'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を最後に直した時刻'),
    sa.ForeignKeyConstraint(['episode_id'], ['episode.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_episode_comment_diff_episode_id'), 'episode_comment_diff', ['episode_id'], unique=False)
    op.create_table('episode_comment_reaction',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('episode_id', sa.Integer(), nullable=False),
    sa.Column('diff_id', sa.Integer(), nullable=False, comment='どの差分まで読んで返したか'),
    sa.Column('character_id', sa.Integer(), nullable=True, comment='反応した人物。空なら語り部'),
    sa.Column('stance', sa.String(), nullable=False, comment='感想/同意/反対/修正案 のいずれか'),
    sa.Column('quote', sa.String(), nullable=True, comment='反応する本文の箇所(本文からそのまま引く)'),
    sa.Column('text', sa.String(), nullable=False, comment='反応の文'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を作った時刻'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を最後に直した時刻'),
    sa.ForeignKeyConstraint(['character_id'], ['character.id'], ),
    sa.ForeignKeyConstraint(['diff_id'], ['episode_comment_diff.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['episode_id'], ['episode.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_episode_comment_reaction_character_id'), 'episode_comment_reaction', ['character_id'], unique=False)
    op.create_index(op.f('ix_episode_comment_reaction_diff_id'), 'episode_comment_reaction', ['diff_id'], unique=False)
    op.create_index(op.f('ix_episode_comment_reaction_episode_id'), 'episode_comment_reaction', ['episode_id'], unique=False)
    op.execute('CREATE OR REPLACE TRIGGER set_updated_at BEFORE UPDATE ON "episode_comment_diff" FOR EACH ROW EXECUTE FUNCTION set_updated_at()')
    op.execute('CREATE OR REPLACE TRIGGER set_updated_at BEFORE UPDATE ON "episode_comment_reaction" FOR EACH ROW EXECUTE FUNCTION set_updated_at()')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_episode_comment_reaction_episode_id'), table_name='episode_comment_reaction')
    op.drop_index(op.f('ix_episode_comment_reaction_diff_id'), table_name='episode_comment_reaction')
    op.drop_index(op.f('ix_episode_comment_reaction_character_id'), table_name='episode_comment_reaction')
    op.drop_table('episode_comment_reaction')
    op.drop_index(op.f('ix_episode_comment_diff_episode_id'), table_name='episode_comment_diff')
    op.drop_table('episode_comment_diff')
