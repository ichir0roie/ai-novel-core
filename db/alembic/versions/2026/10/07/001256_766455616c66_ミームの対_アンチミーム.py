"""ミームの対(アンチミーム)

ミーム(`meme`)に、反転した対のミームを指す `anti_meme_id` を足す。対の二行が互いを指す。
既にあるミームは空のまま残り、次の抽出で AI がアンチミームを作る。

Revision ID: 766455616c66
Revises: fba3b7646598
Create Date: 2026-10-07 00:12:56.912408

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '766455616c66'
down_revision: Union[str, Sequence[str], None] = 'fba3b7646598'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('meme', sa.Column('anti_meme_id', sa.Integer(), nullable=True, comment='反転したミーム(アンチミーム)。対の二行が互いを指す。空なら次の抽出で AI が作る'))
    op.create_index(op.f('ix_meme_anti_meme_id'), 'meme', ['anti_meme_id'], unique=False)
    op.create_foreign_key('meme_anti_meme_id_fkey', 'meme', 'meme', ['anti_meme_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('meme_anti_meme_id_fkey', 'meme', type_='foreignkey')
    op.drop_index(op.f('ix_meme_anti_meme_id'), table_name='meme')
    op.drop_column('meme', 'anti_meme_id')
