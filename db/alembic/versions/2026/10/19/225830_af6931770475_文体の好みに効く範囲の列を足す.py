"""文体の好みに効く範囲の列を足す

文体の好みを、AI が書くすべての文(プロット・来歴・アイデア・ミームなど)に効かせる行(全体)と、話の本文だけに効かせる行(本文)に
分ける。今ある行は、これまでどおり本文だけに効く。

Revision ID: af6931770475
Revises: a42126849c99
Create Date: 2026-10-19 22:58:30.717407

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af6931770475'
down_revision: Union[str, Sequence[str], None] = 'a42126849c99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('style_preference', sa.Column('scope', sa.String(), server_default='本文', nullable=False, comment='効く範囲。全体/本文 のいずれか。全体は AI が書くすべての文に、本文は話の本文だけに効く'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('style_preference', 'scope')
