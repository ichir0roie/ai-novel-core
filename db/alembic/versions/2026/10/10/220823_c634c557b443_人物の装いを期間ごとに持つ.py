"""人物の装いを期間ごとに持つ

人物のパラメータ(`character_parameter`)に装い(`outfit`)の列を足す。身なりと、人目に見える持ち物・武器・傷・印を、
体格と同じく変わった時ごとの行で持ち、見た人に知れる「今の見た目」として渡す。既にある行は空のまま(決めない)。

Revision ID: c634c557b443
Revises: 044cdd645f89
Create Date: 2026-10-10 22:08:23.403617

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c634c557b443'
down_revision: Union[str, Sequence[str], None] = '044cdd645f89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('character_parameter', sa.Column('outfit', sa.String(), nullable=True, comment='装い。身なりと、人目に見える持ち物・武器・傷・印'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('character_parameter', 'outfit')
