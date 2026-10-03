"""アイデアの呼び名の表 idea_recognition を履歴 idea_history に改名する

場所・時代ごとの作中での呼び名を、人物の来歴(character_history)と同じくアイデアの履歴として持つ。列はそのまま。
制約・索引・連番は、表を作ったときの名前(表の名前から付く既定の名前)をそろえて改める。

Revision ID: 129928633f0c
Revises: d92b78b172bf
Create Date: 2026-10-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '129928633f0c'
down_revision: Union[str, Sequence[str], None] = 'd92b78b172bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename(old: str, new: str) -> None:
    op.rename_table(old, new)
    op.execute(f'ALTER SEQUENCE {old}_id_seq RENAME TO {new}_id_seq')
    op.execute(f'ALTER INDEX ix_{old}_idea_id RENAME TO ix_{new}_idea_id')
    for suffix in ('pkey', 'idea_id_fkey', 'location_id_fkey'):
        op.execute(f'ALTER TABLE {new} RENAME CONSTRAINT {old}_{suffix} TO {new}_{suffix}')


def upgrade() -> None:
    """Upgrade schema."""
    _rename('idea_recognition', 'idea_history')


def downgrade() -> None:
    """Downgrade schema."""
    _rename('idea_history', 'idea_recognition')
