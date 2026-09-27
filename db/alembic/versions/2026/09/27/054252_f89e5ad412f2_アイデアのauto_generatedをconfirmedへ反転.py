"""アイデアのauto_generatedをconfirmedへ反転

Revision ID: f89e5ad412f2
Revises: b2334b91ee8d
Create Date: 2026-09-27 05:42:52.268057

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f89e5ad412f2'
down_revision: Union[str, Sequence[str], None] = 'b2334b91ee8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONFIRMED_COMMENT = ('確かめた設定として使ってよいか。本文から自動で足した未確認の候補は false で、'
                      '検索・生成には出ない。確かめたら true にする')
_AUTO_GENERATED_COMMENT = '本文から自動で足した未確認のアイデアか。検索・生成には他と同じく出る。確かめたら false にする'


def upgrade() -> None:
    """auto_generated を反転して confirmed へ移す。既定値が true のまま、新しく足すアイデアは確定済みになる。"""
    with op.batch_alter_table('idea', schema=None) as batch_op:
        batch_op.add_column(sa.Column('confirmed', sa.Boolean(), nullable=False,
                                      server_default=sa.true(), comment=_CONFIRMED_COMMENT))
    op.execute('UPDATE idea SET confirmed = NOT auto_generated')
    with op.batch_alter_table('idea', schema=None) as batch_op:
        batch_op.alter_column('confirmed', server_default=None)
        batch_op.drop_column('auto_generated')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('idea', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_generated', sa.Boolean(), nullable=False,
                                      server_default=sa.false(), comment=_AUTO_GENERATED_COMMENT))
    op.execute('UPDATE idea SET auto_generated = NOT confirmed')
    with op.batch_alter_table('idea', schema=None) as batch_op:
        batch_op.alter_column('auto_generated', server_default=None)
        batch_op.drop_column('confirmed')
