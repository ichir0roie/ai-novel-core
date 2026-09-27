"""出来事と人物に承認フラグを足す

Revision ID: aba4a26c1fd5
Revises: c03cab1e5e7c
Create Date: 2026-09-27 23:17:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aba4a26c1fd5'
down_revision: Union[str, Sequence[str], None] = 'c03cab1e5e7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("event", "character")


def upgrade() -> None:
    """confirmed を足す。既にある出来事・人物は使われてきたものとして 承認 で始め、
    以降のランダム生成は schema.py の既定値どおり 未確認 になる。"""
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column(
                'confirmed', sa.String(), nullable=False, server_default='承認',
                comment='ユーザが確かめたものとして使ってよいか。未確認/承認/非承認 のいずれか。'
                        'ランダム生成の直後は 未確認 で、話・筋書きには使われない。'
                        '確かめたら 承認、無かったことにするなら 非承認 にする'))
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('confirmed', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('confirmed')
