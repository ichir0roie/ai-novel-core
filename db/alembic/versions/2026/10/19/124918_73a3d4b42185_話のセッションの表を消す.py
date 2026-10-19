"""話のセッションの表を消す

語り部と人物役の手番の行は、掛け合いのあいだだけ要る。一手ごとに API(Lambda・db)を往復すると数秒かかるので、
手番の行は語り部と人物役が同じ機械で読み書きする手元のファイル(`data_access_logic/episode_session/store.py`)に移し、
話のセッションの表(`episode_character_session`・`episode_character_session_witness`)は消す。残っていた行も消える。

Revision ID: 73a3d4b42185
Revises: 350bf2aaa976
Create Date: 2026-10-19 12:49:18.295487

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '73a3d4b42185'
down_revision: Union[str, Sequence[str], None] = '350bf2aaa976'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 見聞きする人物の表が外部キーでセッションの表を指すので、先に消す
    op.drop_index(op.f('ix_episode_character_session_witness_character_id'), table_name='episode_character_session_witness')
    op.drop_index(op.f('ix_episode_character_session_witness_episode_character__f24b'), table_name='episode_character_session_witness')
    op.drop_table('episode_character_session_witness')
    op.drop_index(op.f('ix_episode_character_session_character_id'), table_name='episode_character_session')
    op.drop_index(op.f('ix_episode_character_session_episode_id'), table_name='episode_character_session')
    op.drop_table('episode_character_session')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('episode_character_session',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('episode_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('kind', sa.VARCHAR(), autoincrement=False, nullable=False, comment='行の種別。人物/語り/作者 のいずれか'),
    sa.Column('character_id', sa.INTEGER(), autoincrement=False, nullable=True, comment='この手番で動く人物。人物の行だけが持つ'),
    sa.Column('time', sa.BIGINT(), autoincrement=False, nullable=True, comment='この手番の作中の時刻'),
    sa.Column('request', sa.VARCHAR(), autoincrement=False, nullable=False, comment='語り部の要求。その人物にだけ見える・聞こえるようになったことと、この手番で求めること。語りの行では、見聞きする人物に届く状況。作者の行では、語り部が作者に番を渡すときの一言'),
    sa.Column('simultaneous', sa.BOOLEAN(), autoincrement=False, nullable=False, comment='前の手番と同時に動く手番。前の手番の一手を待たずに番が開き、同じ組の一手は次の番で届く'),
    sa.Column('thought', sa.VARCHAR(), autoincrement=False, nullable=True, comment='人物の内心(言葉にしない思い)'),
    sa.Column('action', sa.VARCHAR(), autoincrement=False, nullable=True, comment='人物の行動(外から見える動き)。作者の行では、作者が本文に書いたこと(前の本文からの差分か発言)。空ならまだ動いていない'),
    sa.Column('speech', sa.VARCHAR(), autoincrement=False, nullable=True, comment='人物のセリフ'),
    sa.Column('aim', sa.VARCHAR(), autoincrement=False, nullable=True, comment='この手番での人物の狙い'),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False, comment='行を作った時刻'),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False, comment='行を最後に直した時刻'),
    sa.CheckConstraint("(character_id IS NOT NULL) = (kind::text = '人物'::text)", name=op.f('ck_episode_character_session_character_kind')),
    sa.ForeignKeyConstraint(['character_id'], ['character.id'], name=op.f('episode_character_session_character_id_fkey')),
    sa.ForeignKeyConstraint(['episode_id'], ['episode.id'], name=op.f('episode_character_session_episode_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('episode_character_session_pkey'))
    )
    op.create_index(op.f('ix_episode_character_session_episode_id'), 'episode_character_session', ['episode_id'], unique=False)
    op.create_index(op.f('ix_episode_character_session_character_id'), 'episode_character_session', ['character_id'], unique=False)
    op.create_table('episode_character_session_witness',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('episode_character_session_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('character_id', sa.INTEGER(), autoincrement=False, nullable=False, comment='見聞きする人物'),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False, comment='行を作った時刻'),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False, comment='行を最後に直した時刻'),
    sa.ForeignKeyConstraint(['character_id'], ['character.id'], name=op.f('episode_character_session_witness_character_id_fkey')),
    sa.ForeignKeyConstraint(['episode_character_session_id'], ['episode_character_session.id'], name=op.f('episode_character_session_wit_episode_character_session_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('episode_character_session_witness_pkey')),
    sa.UniqueConstraint('episode_character_session_id', 'character_id', name=op.f('episode_character_session_wit_episode_character_session_id__key'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_episode_character_session_witness_episode_character__f24b'), 'episode_character_session_witness', ['episode_character_session_id'], unique=False)
    op.create_index(op.f('ix_episode_character_session_witness_character_id'), 'episode_character_session_witness', ['character_id'], unique=False)
    op.execute('CREATE OR REPLACE TRIGGER set_updated_at BEFORE UPDATE ON "episode_character_session" FOR EACH ROW EXECUTE FUNCTION set_updated_at()')
    op.execute('CREATE OR REPLACE TRIGGER set_updated_at BEFORE UPDATE ON "episode_character_session_witness" FOR EACH ROW EXECUTE FUNCTION set_updated_at()')
