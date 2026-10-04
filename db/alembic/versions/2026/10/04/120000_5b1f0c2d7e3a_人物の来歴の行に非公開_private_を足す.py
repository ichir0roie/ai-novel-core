"""人物の来歴の行に非公開(private)を足す

Revision ID: 5b1f0c2d7e3a
Revises: 4493f8c00cab
Create Date: 2026-10-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b1f0c2d7e3a'
down_revision: Union[str, Sequence[str], None] = '4493f8c00cab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('character_history', sa.Column('private', sa.Boolean(), server_default='false', nullable=False, comment='非公開。本人・関係のある人物も知らず、知る相手だけが知る'))
    # 今ある行は知る相手だけが知る前提で書いてあるので、関係のある人物に広まらないよう非公開にする
    op.execute("UPDATE character_history SET private = true")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('character_history', 'private')
