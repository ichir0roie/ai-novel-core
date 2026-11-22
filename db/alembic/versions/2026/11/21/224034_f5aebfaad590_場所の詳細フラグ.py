"""場所の詳細フラグ

場所に詳細フラグ(既定 false)を足す。詳細の場所(町の中の場所・周りのエリア・人物の家など)は全体の地図に出さず、
親の場所から開く詳細マップにだけ出す。

Revision ID: f5aebfaad590
Revises: 5b2e8d1c4a7f
Create Date: 2026-11-21 22:40:34.826563

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f5aebfaad590'
down_revision: Union[str, Sequence[str], None] = '5b2e8d1c4a7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('location', sa.Column(
        'map_detail', sa.Boolean(), server_default='false', nullable=False,
        comment='詳細の場所か。町の中の場所・周りのエリア・人物の家など。全体の地図に出さず、'
        '詳細マップ(親の場所から開く)にだけ出す'))


def downgrade() -> None:
    op.drop_column('location', 'map_detail')
