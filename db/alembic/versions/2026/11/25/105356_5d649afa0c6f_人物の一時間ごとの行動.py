"""人物の一時間ごとの行動

人物の一日の行動(人物モード `SimulateDay`)を、暦の一時間ごとに一行で持つ表 event_action を足す。

Revision ID: 5d649afa0c6f
Revises: f5aebfaad590
Create Date: 2026-11-25 10:53:56.556533

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '5d649afa0c6f'
down_revision: Union[str, Sequence[str], None] = 'f5aebfaad590'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXED = ('character_id', 'expansion_id', 'fixed_episode_id', 'fixed_event_id', 'location_id', 'origin', 'time')


def upgrade() -> None:
    op.create_table(
        'event_action',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False, comment='動いた人物'),
        sa.Column('expansion_id', sa.Integer(), nullable=True, comment='この行を足した展開(人物の一日)'),
        sa.Column('time', sa.BigInteger(), nullable=False, comment='その一時間の始まり'),
        sa.Column('location_id', sa.Integer(), nullable=False, comment='その一時間を過ごした場所'),
        sa.Column('kind', sa.String(), nullable=False, comment='行動の種別(眠る・食べる・働く・用事・話す・休む・予定など)'),
        sa.Column('speech', sa.String(), nullable=True, comment='口にした言葉'),
        sa.Column('thought', sa.String(), nullable=True, comment='内心。本人にしか見えない'),
        sa.Column('sleepiness', sa.Integer(), nullable=False, comment='その一時間を終えたときの眠気(0〜100)'),
        sa.Column('hunger', sa.Integer(), nullable=False, comment='その一時間を終えたときの空腹(0〜100)'),
        sa.Column('fixed_event_id', sa.Integer(), nullable=True, comment='作者の出来事の予定で決まった一時間なら、その出来事'),
        sa.Column('fixed_episode_id', sa.Integer(), nullable=True, comment='作者の話の予定で決まった一時間なら、その話'),
        sa.Column('text', sa.String(), nullable=False, comment='その一時間にしたこと'),
        sa.Column('origin', sa.String(), server_default='user', nullable=False,
                  comment='出自。user は作者が作った・直した行、ai は AI が作者の確かめを経ずに足した行。AI は user の行に触らない'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False,
                  comment='行を作った時刻'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False,
                  comment='行を最後に直した時刻'),
        sa.ForeignKeyConstraint(['character_id'], ['character.id']),
        sa.ForeignKeyConstraint(['expansion_id'], ['expansion.id']),
        sa.ForeignKeyConstraint(['fixed_episode_id'], ['episode.id']),
        sa.ForeignKeyConstraint(['fixed_event_id'], ['event.id']),
        sa.ForeignKeyConstraint(['location_id'], ['location.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for column in _INDEXED:
        op.create_index(op.f(f'ix_event_action_{column}'), 'event_action', [column], unique=False)
    op.execute('CREATE OR REPLACE TRIGGER set_updated_at BEFORE UPDATE ON "event_action" '
               'FOR EACH ROW EXECUTE FUNCTION set_updated_at()')


def downgrade() -> None:
    for column in _INDEXED:
        op.drop_index(op.f(f'ix_event_action_{column}'), table_name='event_action')
    op.drop_table('event_action')
