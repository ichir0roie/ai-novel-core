"""人物の決まった居場所の表(character_routine)を足す

Revision ID: b9538cb7f8e7
Revises: 5d649afa0c6f
Create Date: 2026-11-26 12:42:08.733906

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import db.schema


# revision identifiers, used by Alembic.
revision: str = 'b9538cb7f8e7'
down_revision: Union[str, Sequence[str], None] = '5d649afa0c6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('character_routine',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('character_id', sa.Integer(), nullable=True),
    sa.Column('location_id', sa.Integer(), nullable=False, comment='決まった居場所(詳細の場所)'),
    sa.Column('hour_from', sa.Integer(), nullable=False, comment='毎日、ここにいる時間の始まりの時'),
    sa.Column('hour_to', sa.Integer(), nullable=False, comment='毎日、ここにいる時間の終わりの時(この時からはいない)。始まり以下なら日付をまたぐ'),
    sa.Column('text', sa.String(), server_default='', nullable=False, comment='ここでしていること(店を開けている・帳場に座っているなど)'),
    sa.Column('start', db.schema.StampType(), nullable=True, comment='この決まりが始まった時刻。空なら初めから'),
    sa.Column('end', db.schema.StampType(), nullable=True, comment='この決まりが終わった時刻(この時刻からは効かない)。空ならまだ続く'),
    sa.Column('origin', sa.String(), server_default='user', nullable=False, comment='出自。user は作者が作った・直した行、ai は AI が作者の確かめを経ずに足した行。AI は user の行に触らない'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を作った時刻'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='行を最後に直した時刻'),
    sa.ForeignKeyConstraint(['character_id'], ['character.id'], ),
    sa.ForeignKeyConstraint(['location_id'], ['location.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_character_routine_character_id'), 'character_routine', ['character_id'], unique=False)
    op.create_index(op.f('ix_character_routine_location_id'), 'character_routine', ['location_id'], unique=False)
    op.create_index(op.f('ix_character_routine_origin'), 'character_routine', ['origin'], unique=False)
    op.execute('CREATE OR REPLACE TRIGGER set_updated_at BEFORE UPDATE ON "character_routine" FOR EACH ROW EXECUTE FUNCTION set_updated_at()')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_character_routine_origin'), table_name='character_routine')
    op.drop_index(op.f('ix_character_routine_location_id'), table_name='character_routine')
    op.drop_index(op.f('ix_character_routine_character_id'), table_name='character_routine')
    op.drop_table('character_routine')
