"""人物の居場所のテーブルを character_location にする

Revision ID: d8f359a0f934
Revises: fc6944ff00e7
Create Date: 2026-09-29 18:03:14.002457

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f359a0f934'
down_revision: Union[str, Sequence[str], None] = 'fc6944ff00e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table('character_place', 'character_location')


def downgrade() -> None:
    """Downgrade schema."""
    op.rename_table('character_location', 'character_place')
