"""アイデアの場所を履歴の行へ移し_非公開の行を足し_ミームの元を話の本文にする

Revision ID: 4493f8c00cab
Revises: 94e049fee804
Create Date: 2026-10-04 00:00:58.651544

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4493f8c00cab'
down_revision: Union[str, Sequence[str], None] = '94e049fee804'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('idea_history', sa.Column('private', sa.Boolean(), server_default='false', nullable=False, comment='非公開。効く場所・期間に住む人物も知らず、知る相手だけが知る。作中の呼び名にも使わない'))
    # アイデア本体の効く場所は、履歴の非公開の行へ移す(作中の人物には知らせず、場所で絞るのにだけ使う)。
    # 同じ場所の行がすでにあれば足さない
    op.execute("""
        INSERT INTO idea_history (idea_id, location_id, name, private)
        SELECT idea.id, idea.location_id, idea.name, true
        FROM idea
        WHERE idea.location_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM idea_history AS row
                          WHERE row.idea_id = idea.id AND row.location_id = idea.location_id)
    """)
    op.drop_index(op.f('ix_idea_location_id'), table_name='idea')
    op.drop_constraint(op.f('idea_location_id_fkey'), 'idea', type_='foreignkey')
    op.drop_column('idea', 'location_id')
    # ミームはアイデア・人物から抜き出さず、話の本文から抜き出す。いまある話は抜き出し済みとして扱う
    op.drop_column('idea', 'meme_seeded')
    op.drop_column('character', 'meme_seeded')
    op.add_column('episode', sa.Column('meme_seeded', sa.Boolean(), server_default=sa.true(), nullable=False, comment='ミームを抜き出し済みか。false に戻すと、次の抽出で抜き出し直す'))
    op.alter_column('episode', 'meme_seeded', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('episode', 'meme_seeded')
    op.add_column('character', sa.Column('meme_seeded', sa.BOOLEAN(), server_default=sa.true(), autoincrement=False, nullable=False, comment='ミームを抜き出し済みか。false に戻すと、次の抽出で抜き出し直す'))
    op.alter_column('character', 'meme_seeded', server_default=None)
    op.add_column('idea', sa.Column('meme_seeded', sa.BOOLEAN(), server_default=sa.true(), autoincrement=False, nullable=False, comment='ミームを抜き出し済みか。false に戻すと、次の抽出で抜き出し直す'))
    op.alter_column('idea', 'meme_seeded', server_default=None)
    op.add_column('idea', sa.Column('location_id', sa.INTEGER(), autoincrement=False, nullable=True, comment='効く場所。この場所とその配下で効く。空ならどこにも効かない'))
    op.create_foreign_key(op.f('idea_location_id_fkey'), 'idea', 'location', ['location_id'], ['id'])
    op.create_index(op.f('ix_idea_location_id'), 'idea', ['location_id'], unique=False)
    # 非公開の行の場所を本体へ戻す(一つに決まらなければ id の小さい行)
    op.execute("""
        UPDATE idea SET location_id = (
            SELECT row.location_id FROM idea_history AS row
            WHERE row.idea_id = idea.id AND row.private AND row.location_id IS NOT NULL
            ORDER BY row.id LIMIT 1)
    """)
    op.drop_column('idea_history', 'private')
