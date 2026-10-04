"""人物の来歴とアイデアの履歴の非公開(private)を消し、知る相手だけで知らせる

Revision ID: 7c4e1a9b3f62
Revises: 5b2e7c9a1d34
Create Date: 2026-10-04 23:59:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c4e1a9b3f62'
down_revision: Union[str, Sequence[str], None] = '5b2e7c9a1d34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 公開の行は知る相手の行が無くても知られていたので、知る相手の行に写す。
    # 人物の来歴の公開の行は本人が知っていた(関係のある人物はその時刻ごとに変わるので写せない)
    op.execute("""
        INSERT INTO character_history_knower (character_history_id, knower_id)
        SELECT row.id, row.character_id
        FROM character_history AS row
        WHERE NOT row.private
          AND NOT EXISTS (SELECT 1 FROM character_history_knower AS knower
                          WHERE knower.character_history_id = row.id AND knower.knower_id = row.character_id)
    """)
    # アイデアの履歴の公開の行は、効く場所(空なら最上位の場所すべて)に効き始めから住む人物が知っていた
    op.execute("""
        INSERT INTO idea_history_knower (idea_history_id, location_id, start)
        SELECT row.id, place.id, row.start
        FROM idea_history AS row
        JOIN location AS place
          ON place.id = row.location_id OR (row.location_id IS NULL AND place.parent_id IS NULL)
        WHERE NOT row.private
          AND NOT EXISTS (SELECT 1 FROM idea_history_knower AS knower
                          WHERE knower.idea_history_id = row.id AND knower.location_id = place.id)
    """)
    op.drop_column('idea_history', 'private')
    op.drop_column('character_history', 'private')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('character_history', sa.Column('private', sa.Boolean(), server_default='false', nullable=False, comment='非公開。本人・関係のある人物も知らず、知る相手だけが知る'))
    op.add_column('idea_history', sa.Column('private', sa.Boolean(), server_default='false', nullable=False, comment='非公開。効く場所・期間に住む人物も知らず、知る相手だけが知る。作中の呼び名にも使わない'))
    # 今ある行は知る相手だけが知るので、ほかの人物に広まらないよう非公開にする
    op.execute("UPDATE character_history SET private = true")
    op.execute("UPDATE idea_history SET private = true")
