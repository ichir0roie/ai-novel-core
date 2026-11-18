"""出来事の start を time にまとめる

Revision ID: c75dfd4e2973
Revises: 85e5fb9b8546
Create Date: 2026-11-18 22:29:15.476901

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c75dfd4e2973'
down_revision: Union[str, Sequence[str], None] = '85e5fb9b8546'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('UPDATE event SET time = start WHERE start IS NOT NULL AND start <> time')
    op.alter_column('event', 'time',
               existing_type=sa.BIGINT(),
               comment='起きた時刻。期間のある出来事なら始まりで、終わりは end',
               existing_nullable=False)
    op.drop_column('event', 'start')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('event', sa.Column('start', sa.BIGINT(), autoincrement=False, nullable=True))
    # 前のコードは start のある出来事を人物をふさぐ期間と読んだので、終わりのある出来事にだけ戻す
    op.execute('UPDATE event SET start = time WHERE "end" IS NOT NULL')
    op.alter_column('event', 'time',
               existing_type=sa.BIGINT(),
               comment=None,
               existing_comment='起きた時刻。期間のある出来事なら始まりで、終わりは end',
               existing_nullable=False)
    # ### end Alembic commands ###
