"""出来事の重視度

出来事に重視度(1〜10、既定 5)を足す。出来事の年表は、重視度の大きい出来事ほど左の層に置く。

Revision ID: 5b2e8d1c4a7f
Revises: 742356006819
Create Date: 2026-11-20 13:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '5b2e8d1c4a7f'
down_revision: Union[str, Sequence[str], None] = '742356006819'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('event', sa.Column(
        'importance', sa.Integer(), server_default='5', nullable=False,
        comment='重視度(1〜10)。大きいほど出来事の年表で左の層に置く'))


def downgrade() -> None:
    op.drop_column('event', 'importance')
