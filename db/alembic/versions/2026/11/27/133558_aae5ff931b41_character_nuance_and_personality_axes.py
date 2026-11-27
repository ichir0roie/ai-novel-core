"""人物の癖(相手ごとの癖も)と思い込みの表(character_nuance)と、性格の三つの軸(自制心・見捨てられ不安・親密さの回避)と、話の要約の表(episode_summary)を足す

Revision ID: aae5ff931b41
Revises: b9538cb7f8e7
Create Date: 2026-11-27 13:35:58.120780

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import db.schema


# revision identifiers, used by Alembic.
revision: str = 'aae5ff931b41'
down_revision: Union[str, Sequence[str], None] = 'b9538cb7f8e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('character_nuance',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('character_id', sa.Integer(), nullable=False, comment='振る舞いの主の人物'),
    sa.Column('start', db.schema.StampType(), nullable=True, comment='効き始める時刻。空なら初めから'),
    sa.Column('end', db.schema.StampType(), nullable=True, comment='効き終わる時刻(この時刻からは効かない)。空ならまだ続く'),
    sa.Column('kind', sa.String(), server_default='癖', nullable=False, comment='種別。「癖」(場面と振る舞いの組)か「思い込み」(人や世の中をまずこう受け取る)'),
    sa.Column('situation', sa.String(), nullable=True, comment='癖の出る場面(止められたとき・褒められたとき・初対面の相手と など)。思い込みは空'),
    sa.Column('target_character_id', sa.Integer(), nullable=True, comment='癖の出る相手。空なら相手を限らない。思い込みは空'),
    sa.Column('text', sa.String(), nullable=False, comment='癖なら、その場面でする振る舞い。思い込みなら、その中身'),
    sa.Column('origin', sa.String(), server_default='user', nullable=False, comment='出自。user は作者が作った・直した行、ai は AI が作者の確かめを経ずに足した行。AI は user の行に触らない'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を作った時刻'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を最後に直した時刻'),
    sa.CheckConstraint("kind = '癖' OR target_character_id IS NULL", name='ck_character_nuance_belief_target'),
    sa.CheckConstraint("kind <> '癖' OR situation IS NOT NULL", name='ck_character_nuance_habit_situation'),
    sa.CheckConstraint('"end" IS NULL OR start IS NULL OR start < "end"', name='ck_character_nuance_span'),
    sa.ForeignKeyConstraint(['character_id'], ['character.id'], ),
    sa.ForeignKeyConstraint(['target_character_id'], ['character.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_character_nuance_character_id'), 'character_nuance', ['character_id'], unique=False)
    op.create_index(op.f('ix_character_nuance_origin'), 'character_nuance', ['origin'], unique=False)
    op.create_index(op.f('ix_character_nuance_target_character_id'), 'character_nuance', ['target_character_id'], unique=False)
    op.add_column('character_parameter', sa.Column('self_control', db.schema.PersonalityLevelType(), nullable=True, comment='自制心。目先の欲・衝動を抑え、決めたことを続けられるか'))
    op.add_column('character_parameter', sa.Column('attachment_anxiety', db.schema.PersonalityLevelType(), nullable=True, comment='見捨てられ不安。近しい相手が離れていくことを恐れ、気持ちを確かめたがるか'))
    op.add_column('character_parameter', sa.Column('intimacy_avoidance', db.schema.PersonalityLevelType(), nullable=True, comment='親密さの回避。人に頼らず、近づかれると距離を取るか'))
    op.create_foreign_key('character_parameter_self_control_fkey', 'character_parameter', 'personality_level', ['self_control'], ['id'])
    op.create_foreign_key('character_parameter_intimacy_avoidance_fkey', 'character_parameter', 'personality_level', ['intimacy_avoidance'], ['id'])
    op.create_foreign_key('character_parameter_attachment_anxiety_fkey', 'character_parameter', 'personality_level', ['attachment_anxiety'], ['id'])
    op.execute('CREATE OR REPLACE TRIGGER set_updated_at BEFORE UPDATE ON "character_nuance" FOR EACH ROW EXECUTE FUNCTION set_updated_at()')
    op.create_table('episode_summary',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('episode_id', sa.Integer(), nullable=False),
    sa.Column('source_hash', sa.String(), nullable=False, comment='要約した本文の sha256。本文と食い違ったら作り直す'),
    sa.Column('text', sa.String(), nullable=False, comment='要約。場面ごとに、居合わせた人物と、起きたこと・交わした言葉'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を作った時刻'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を最後に直した時刻'),
    sa.ForeignKeyConstraint(['episode_id'], ['episode.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_episode_summary_episode_id'), 'episode_summary', ['episode_id'], unique=True)
    op.execute('CREATE OR REPLACE TRIGGER set_updated_at BEFORE UPDATE ON "episode_summary" FOR EACH ROW EXECUTE FUNCTION set_updated_at()')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_episode_summary_episode_id'), table_name='episode_summary')
    op.drop_table('episode_summary')
    for column in ('intimacy_avoidance', 'attachment_anxiety', 'self_control'):
        op.drop_constraint(f'character_parameter_{column}_fkey', 'character_parameter', type_='foreignkey')
        op.drop_column('character_parameter', column)
    op.drop_index(op.f('ix_character_nuance_target_character_id'), table_name='character_nuance')
    op.drop_index(op.f('ix_character_nuance_origin'), table_name='character_nuance')
    op.drop_index(op.f('ix_character_nuance_character_id'), table_name='character_nuance')
    op.drop_table('character_nuance')
