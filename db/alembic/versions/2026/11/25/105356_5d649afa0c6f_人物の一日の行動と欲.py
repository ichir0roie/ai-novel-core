"""人物の一日の行動と欲

人物モード(`SimulateDay`)のための表と列を足す。

- event_action: 人物の一日の行動を、暦の一時間ごとに一行で持つ
- character_day: 人物の一日ごとの、欲の満ち足り方と行動量と、眠った時刻
- character_parameter: 食欲・睡眠欲・性欲の段(空なら人物モードが年齢から決める)

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

_ACTION_INDEXED = ('character_id', 'expansion_id', 'fixed_episode_id', 'fixed_event_id', 'location_id', 'origin', 'time')
_DAY_INDEXED = ('character_id', 'date', 'expansion_id', 'origin')
_NEEDS = (
    ('appetite', '食欲。人物モードで、空腹の増え方'),
    ('sleep_drive', '睡眠欲。人物モードで、眠気の増え方と、眠りの長さ'),
    ('libido', '性欲。人物モードで、人と触れ合いたい欲の増え方'),
)
_INFLUENCE_OLD = '影響力。町・組織での立場の重さ。人物モードで、一手が世界を動かせる幅と、ほかの人物の一手から受ける影響の受けにくさ'
_INFLUENCE_NEW = '影響力。町・組織での立場の重さ。人物モードで、一日の記録が世界を動かせる幅と、ほかの人物の一日から受ける影響の受けにくさ'
_ORIGIN_COMMENT = '出自。user は作者が作った・直した行、ai は AI が作者の確かめを経ずに足した行。AI は user の行に触らない'


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column('origin', sa.String(), server_default='user', nullable=False, comment=_ORIGIN_COMMENT),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False,
                  comment='行を作った時刻'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False,
                  comment='行を最後に直した時刻'),
    ]


def _updated_at_trigger(table: str) -> None:
    op.execute(f'CREATE OR REPLACE TRIGGER set_updated_at BEFORE UPDATE ON "{table}" '
               'FOR EACH ROW EXECUTE FUNCTION set_updated_at()')


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
        sa.Column('desire', sa.Integer(), nullable=False, comment='その一時間を終えたときの、人と触れ合いたい欲(0〜100)'),
        sa.Column('load', sa.Integer(), nullable=False,
                  comment='その一時間の行動量(外に出た・戦った・働いた・傷つけた・人を変えたの重みの和)'),
        sa.Column('fixed_event_id', sa.Integer(), nullable=True, comment='作者の出来事の予定で決まった一時間なら、その出来事'),
        sa.Column('fixed_episode_id', sa.Integer(), nullable=True, comment='作者の話の予定で決まった一時間なら、その話'),
        sa.Column('text', sa.String(), nullable=False, comment='その一時間にしたこと'),
        *_timestamps(),
        sa.ForeignKeyConstraint(['character_id'], ['character.id']),
        sa.ForeignKeyConstraint(['expansion_id'], ['expansion.id']),
        sa.ForeignKeyConstraint(['fixed_episode_id'], ['episode.id']),
        sa.ForeignKeyConstraint(['fixed_event_id'], ['event.id']),
        sa.ForeignKeyConstraint(['location_id'], ['location.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for column in _ACTION_INDEXED:
        op.create_index(op.f(f'ix_event_action_{column}'), 'event_action', [column], unique=False)
    _updated_at_trigger('event_action')

    op.create_table(
        'character_day',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False, comment='人物'),
        sa.Column('expansion_id', sa.Integer(), nullable=True, comment='この行を足した展開(人物の一日)'),
        sa.Column('date', sa.BigInteger(), nullable=False, comment='その日の 0 時'),
        sa.Column('food', sa.Integer(), nullable=False, comment='食欲の満ち足り方(0〜100)'),
        sa.Column('sleep', sa.Integer(), nullable=False, comment='睡眠欲の満ち足り方(0〜100)'),
        sa.Column('touch', sa.Integer(), nullable=False, comment='人と触れ合いたい欲(性欲)の満ち足り方(0〜100)'),
        sa.Column('load', sa.Integer(), nullable=False, comment='その日の行動量'),
        sa.Column('bedtime', sa.Integer(), nullable=False,
                  comment='その夜に眠った時刻(その日の一時間の番号。一日の時間の数以上なら、日付が変わってから眠った)'),
        *_timestamps(),
        sa.ForeignKeyConstraint(['character_id'], ['character.id']),
        sa.ForeignKeyConstraint(['expansion_id'], ['expansion.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('character_id', 'date'),
    )
    for column in _DAY_INDEXED:
        op.create_index(op.f(f'ix_character_day_{column}'), 'character_day', [column], unique=False)
    _updated_at_trigger('character_day')

    for column, comment in _NEEDS:
        op.add_column('character_parameter', sa.Column(column, sa.Integer(), nullable=True, comment=comment))
        op.create_foreign_key(None, 'character_parameter', 'personality_level', [column], ['id'])
    op.alter_column('character_parameter', 'influence', existing_type=sa.Integer(), existing_nullable=True,
                    comment=_INFLUENCE_NEW, existing_comment=_INFLUENCE_OLD)


def downgrade() -> None:
    op.alter_column('character_parameter', 'influence', existing_type=sa.Integer(), existing_nullable=True,
                    comment=_INFLUENCE_OLD, existing_comment=_INFLUENCE_NEW)
    for column, _ in reversed(_NEEDS):
        op.drop_constraint(f'character_parameter_{column}_fkey', 'character_parameter', type_='foreignkey')
        op.drop_column('character_parameter', column)
    for column in _DAY_INDEXED:
        op.drop_index(op.f(f'ix_character_day_{column}'), table_name='character_day')
    op.drop_table('character_day')
    for column in _ACTION_INDEXED:
        op.drop_index(op.f(f'ix_event_action_{column}'), table_name='event_action')
    op.drop_table('event_action')
