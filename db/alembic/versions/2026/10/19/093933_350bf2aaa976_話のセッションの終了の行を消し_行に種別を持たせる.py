"""話のセッションの終了の行を消し、行に種別を持たせる

人物役は表を見張らず、語り部が番の行の id を送るので、話が終わった合図の終了の行(`closing`)は要らない。終了の行を消して列も消す。
作者と代わる代わる書くセッションは、終えるときに行を消す(`ClearSession`)。
人物の有無と作者の印(`author`)から推し量っていた行の種類を、種別(`kind`: 人物/語り/作者)の列一つで持つ。

Revision ID: 350bf2aaa976
Revises: 5d77ceb37e00
Create Date: 2026-10-19 09:39:33.143269

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '350bf2aaa976'
down_revision: Union[str, Sequence[str], None] = '5d77ceb37e00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "episode_character_session"
CHECK = "ck_episode_character_session_character_kind"


def upgrade() -> None:
    """Upgrade schema."""
    # 見聞きする人物の行は、外部キーの ON DELETE CASCADE で db がいっしょに消す
    op.execute(f"DELETE FROM {TABLE} WHERE closing")
    op.add_column(TABLE, sa.Column('kind', sa.String(), nullable=True, comment='行の種別。人物/語り/作者 のいずれか'))
    op.execute(f"UPDATE {TABLE} SET kind = CASE WHEN author THEN '作者' WHEN character_id IS NULL THEN '語り' ELSE '人物' END")
    op.alter_column(TABLE, 'kind', existing_type=sa.String(), nullable=False)
    op.create_check_constraint(CHECK, TABLE, "(character_id IS NOT NULL) = (kind = '人物')")
    op.alter_column(TABLE, 'character_id',
               existing_type=sa.INTEGER(),
               comment='この手番で動く人物。人物の行だけが持つ',
               existing_comment='この手番で動く人物。空なら語りの行',
               existing_nullable=True)
    op.drop_column(TABLE, 'author')
    op.drop_column(TABLE, 'closing')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(TABLE, sa.Column('closing', sa.BOOLEAN(), server_default='false', autoincrement=False, nullable=False, comment='話が終わった合図。人物役はこの行を読んだら止まる'))
    op.add_column(TABLE, sa.Column('author', sa.BOOLEAN(), server_default='false', autoincrement=False, nullable=False, comment='作者の行。人物は空で、作者が書いたことを行動に持つ'))
    op.execute(f"UPDATE {TABLE} SET author = (kind = '作者')")
    op.alter_column(TABLE, 'character_id',
               existing_type=sa.INTEGER(),
               comment='この手番で動く人物。空なら語りの行',
               existing_comment='この手番で動く人物。人物の行だけが持つ',
               existing_nullable=True)
    op.drop_constraint(CHECK, TABLE, type_='check')
    op.drop_column(TABLE, 'kind')
