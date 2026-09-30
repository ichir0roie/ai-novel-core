"""話に名前だけ出る人物を episode_character に区別して持つ

Revision ID: 4b7e2c91d0a3
Revises: cdb295fb8717
Create Date: 2026-10-01 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b7e2c91d0a3'
down_revision: Union[str, Sequence[str], None] = 'cdb295fb8717'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('episode_character', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'mentioned', sa.Boolean(), nullable=False, server_default=sa.false(),
            comment='この話に登場せず、プロット・本文に名前が出るだけの人物か。'
                    '推敲・プロット補完・枠の生成のたびに、プロット・本文から拾い直す'))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM episode_character WHERE mentioned")
    with op.batch_alter_table('episode_character', schema=None) as batch_op:
        batch_op.drop_column('mentioned')
