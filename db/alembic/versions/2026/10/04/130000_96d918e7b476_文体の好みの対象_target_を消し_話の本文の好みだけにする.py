"""文体の好みの対象 target を消し、話の本文の好みだけにする

Revision ID: 96d918e7b476
Revises: 5b1f0c2d7e3a
Create Date: 2026-10-04 04:25:29.107462

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96d918e7b476'
down_revision: Union[str, Sequence[str], None] = '5b1f0c2d7e3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 話の本文に効いていた shared・episode の行だけを残す(story・event・idea の行は何にも効いていなかった)
    op.execute("DELETE FROM style_preference WHERE target NOT IN ('shared', 'episode')")
    op.drop_constraint(op.f('style_preference_target_key'), 'style_preference', type_='unique')
    op.drop_column('style_preference', 'target')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('style_preference', sa.Column('target', sa.VARCHAR(), autoincrement=False, nullable=True, comment='効く対象。shared はどの対象にも効き、episode などはその対象(`ai/instructions/style.py` の STYLE_BASES)だけに効く'))
    # 対象ごとに一行だったので、一番古い行を shared、ほかを episode に戻す(三行以上あれば戻せない)
    op.execute("UPDATE style_preference SET target = CASE WHEN id = (SELECT min(id) FROM style_preference) "
               "THEN 'shared' ELSE 'episode' END")
    op.alter_column('style_preference', 'target', nullable=False)
    op.create_unique_constraint(op.f('style_preference_target_key'), 'style_preference', ['target'], postgresql_nulls_not_distinct=False)
