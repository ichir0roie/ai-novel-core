"""話のセッションの語りの行と、見聞きする人物

話のセッション(`episode_character_session`)の人物を空にできるようにし、人物の無い行を語りの行(その場の何人もに
見える・聞こえる状況)にする。行(語りか人物の一手)を見聞きする人物の表 `episode_character_session_witness` を足す。
人物役は自分の番に、前の自分の番から後の、自分が見聞きする行を受け取る。既にある行は見聞きする人物を持たない。

Revision ID: 044cdd645f89
Revises: b7c3e9a10f42
Create Date: 2026-10-09 15:16:33.795628

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '044cdd645f89'
down_revision: Union[str, Sequence[str], None] = 'b7c3e9a10f42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('episode_character_session_witness',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('episode_character_session_id', sa.Integer(), nullable=False),
    sa.Column('character_id', sa.Integer(), nullable=False, comment='見聞きする人物'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を作った時刻'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を最後に直した時刻'),
    sa.ForeignKeyConstraint(['character_id'], ['character.id'], ),
    sa.ForeignKeyConstraint(['episode_character_session_id'], ['episode_character_session.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('episode_character_session_id', 'character_id')
    )
    op.create_index(op.f('ix_episode_character_session_witness_character_id'), 'episode_character_session_witness', ['character_id'], unique=False)
    op.create_index(op.f('ix_episode_character_session_witness_episode_character_session_id'), 'episode_character_session_witness', ['episode_character_session_id'], unique=False)
    op.alter_column('episode_character_session', 'character_id',
               existing_type=sa.INTEGER(),
               nullable=True,
               comment='この手番で動く人物。空なら語りの行',
               existing_comment='この手番で動く人物')
    op.alter_column('episode_character_session', 'request',
               existing_type=sa.VARCHAR(),
               comment='語り部の要求。その人物にだけ見える・聞こえるようになったことと、この手番で求めること。語りの行では、見聞きする人物に届く状況',
               existing_comment='語り部の要求。前の手番から、その人物に見える・聞こえるようになったこと(状況の差分)と、この手番で求めること',
               existing_nullable=False)
    op.execute('CREATE OR REPLACE TRIGGER set_updated_at BEFORE UPDATE ON "episode_character_session_witness" FOR EACH ROW EXECUTE FUNCTION set_updated_at()')


def downgrade() -> None:
    """Downgrade schema."""
    # 人物を空にできなくする前に、語りの行を消す(見聞きする人物の行は cascade で消える)
    op.execute("DELETE FROM episode_character_session WHERE character_id IS NULL")
    op.alter_column('episode_character_session', 'request',
               existing_type=sa.VARCHAR(),
               comment='語り部の要求。前の手番から、その人物に見える・聞こえるようになったこと(状況の差分)と、この手番で求めること',
               existing_comment='語り部の要求。その人物にだけ見える・聞こえるようになったことと、この手番で求めること。語りの行では、見聞きする人物に届く状況',
               existing_nullable=False)
    op.alter_column('episode_character_session', 'character_id',
               existing_type=sa.INTEGER(),
               nullable=False,
               comment='この手番で動く人物',
               existing_comment='この手番で動く人物。空なら語りの行')
    op.drop_index(op.f('ix_episode_character_session_witness_episode_character_session_id'), table_name='episode_character_session_witness')
    op.drop_index(op.f('ix_episode_character_session_witness_character_id'), table_name='episode_character_session_witness')
    op.drop_table('episode_character_session_witness')
