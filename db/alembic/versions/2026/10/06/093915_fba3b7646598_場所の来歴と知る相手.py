"""場所の来歴と知る相手

場所(`location`)に、起きた年ごとの来歴の行(`location_history`)と、その行を知る相手(`location_history_knower`)を足す。
人物の来歴・アイデアの履歴と同じ形。

Revision ID: fba3b7646598
Revises: 3e9d5b7a2c18
Create Date: 2026-10-06 09:39:15.468867

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fba3b7646598'
down_revision: Union[str, Sequence[str], None] = '3e9d5b7a2c18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('location_history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('location_id', sa.Integer(), nullable=False),
    sa.Column('start', sa.Integer(), nullable=True, comment='起きた年(この来歴が効き始める年)。空なら年が決まっていない(話・出来事には渡さない)'),
    sa.Column('description', sa.String(), nullable=False, comment='来歴'),
    sa.ForeignKeyConstraint(['location_id'], ['location.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_location_history_location_id'), 'location_history', ['location_id'], unique=False)
    op.create_table('location_history_knower',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('location_history_id', sa.Integer(), nullable=False),
    sa.Column('knower_id', sa.Integer(), nullable=True, comment='知る人物'),
    sa.Column('location_id', sa.Integer(), nullable=True, comment='知る場所。その時刻にこの場所(配下も含む)に住む人物が知る'),
    sa.Column('start', sa.BigInteger(), nullable=True, comment='知った時刻。空ならいつ知ったか決まっておらず、人物役には渡さない'),
    sa.CheckConstraint('(knower_id IS NULL) <> (location_id IS NULL)', name='ck_location_history_knower_one_knower'),
    sa.ForeignKeyConstraint(['knower_id'], ['character.id'], ),
    sa.ForeignKeyConstraint(['location_history_id'], ['location_history.id'], ),
    sa.ForeignKeyConstraint(['location_id'], ['location.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('location_history_id', 'knower_id'),
    sa.UniqueConstraint('location_history_id', 'location_id')
    )
    op.create_index(op.f('ix_location_history_knower_knower_id'), 'location_history_knower', ['knower_id'], unique=False)
    op.create_index(op.f('ix_location_history_knower_location_history_id'), 'location_history_knower', ['location_history_id'], unique=False)
    op.create_index(op.f('ix_location_history_knower_location_id'), 'location_history_knower', ['location_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_location_history_knower_location_id'), table_name='location_history_knower')
    op.drop_index(op.f('ix_location_history_knower_location_history_id'), table_name='location_history_knower')
    op.drop_index(op.f('ix_location_history_knower_knower_id'), table_name='location_history_knower')
    op.drop_table('location_history_knower')
    op.drop_index(op.f('ix_location_history_location_id'), table_name='location_history')
    op.drop_table('location_history')
