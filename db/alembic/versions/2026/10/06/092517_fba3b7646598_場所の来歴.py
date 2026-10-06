"""場所の来歴

場所(`location`)に、起きた年ごとの来歴の行(`location_history`)を足す。関係の来歴(`character_relation_history`)と同じ形。

Revision ID: fba3b7646598
Revises: 3e9d5b7a2c18
Create Date: 2026-10-06 09:25:17.678647

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


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_location_history_location_id'), table_name='location_history')
    op.drop_table('location_history')
