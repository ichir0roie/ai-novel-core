"""同期フラグと抜き出し済みの印を消す

Revision ID: 57b0b8a7ff35
Revises: af6931770475
Create Date: 2026-10-20 03:14:06.492669

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57b0b8a7ff35'
down_revision: Union[str, Sequence[str], None] = 'af6931770475'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('character', 'event_seeded')
    op.drop_column('episode', 'synced')
    op.drop_column('episode', 'event_seeded')
    op.drop_column('episode', 'meme_seeded')
    op.drop_column('event', 'event_seeded')
    op.drop_column('event', 'meme_seeded')
    op.drop_column('oracle', 'meme_seeded')


def downgrade() -> None:
    """Downgrade schema."""
    # 行のある表に NOT NULL の列を戻すので、既定値を false にして足す
    op.add_column('oracle', sa.Column('meme_seeded', sa.Boolean(), nullable=False, server_default=sa.false(),
                                      comment='ミームを抜き出し済みか。false に戻すと、次の抽出で抜き出し直す'))
    op.add_column('event', sa.Column('meme_seeded', sa.Boolean(), nullable=False, server_default=sa.false(),
                                     comment='ミームを抜き出し済みか。false に戻すと、次の抽出で抜き出し直す'))
    op.add_column('event', sa.Column('event_seeded', sa.Boolean(), nullable=False, server_default=sa.false(),
                                     comment='出来事の種を抜き出し済みか。false に戻すと、次の毎日のルーチンで抜き出し直す'))
    op.add_column('episode', sa.Column('meme_seeded', sa.Boolean(), nullable=False, server_default=sa.false(),
                                       comment='ミームを抜き出し済みか。false に戻すと、次の抽出で抜き出し直す'))
    op.add_column('episode', sa.Column('event_seeded', sa.Boolean(), nullable=False, server_default=sa.false(),
                                       comment='出来事の種を抜き出し済みか。false に戻すと、次の毎日のルーチンで抜き出し直す'))
    op.add_column('episode', sa.Column('synced', sa.Boolean(), nullable=False, server_default=sa.false(),
                                       comment='同期フラグ。この話の出来事・行動が台帳へ戻してあるか。自動生成時はオン、手で書いたときはオフ。'
                                               'オフの話があるあいだは、次の話の材料を読み出せない'))
    op.add_column('character', sa.Column('event_seeded', sa.Boolean(), nullable=False, server_default=sa.false(),
                                         comment='出来事の種を抜き出し済みか。false に戻すと、次の毎日のルーチンで抜き出し直す'))
