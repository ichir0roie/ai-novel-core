"""始まりの空いた知る相手_アイデアの履歴_関係に時刻を入れる

人物役には始まりの空いた行を渡さなくなったので、今ある空の行を、いつからか分かる時刻で埋める。

- 知る相手: 知る人物の生まれ。場所なら、知られる行の始まり(人物・スキルの来歴は年の初め)か、場所のできた時刻
- アイデアの履歴: アイデアの始まり、効く場所のできた時刻、いちばん早い人物の生まれ、の順に先に決まっているもの
- 関係: 二人のうち後に生まれた方の生まれ

Revision ID: 3e9d5b7a2c18
Revises: cc1b4e64b408
Create Date: 2026-10-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e9d5b7a2c18'
down_revision: Union[str, Sequence[str], None] = 'cc1b4e64b408'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_COMMENT = '知った時刻。空なら初めから知っている'
_NEW_COMMENT = '知った時刻。空ならいつ知ったか決まっておらず、人物役には渡さない'
_KNOWER_TABLES = ('character_history_knower', 'character_skill_history_knower', 'idea_history_knower')
# 人物の生まれは `character_parameter` の一番早い行の始まり(`Character.start`)。
# 年の整数を、その年の初めの時刻の列の値(`db.stamp.Stamp.to_int`)にする
_YEAR_START = '{year}::bigint * 10000000000 + 101000000'


def _set_comment(comment: str, existing: str) -> None:
    for table in _KNOWER_TABLES:
        op.alter_column(table, 'start', comment=comment, existing_comment=existing,
                        existing_type=sa.BigInteger(), existing_nullable=True)


def upgrade() -> None:
    """Upgrade schema."""
    _set_comment(_NEW_COMMENT, _OLD_COMMENT)
    op.execute("""
        UPDATE idea_history h SET start = COALESCE(
            (SELECT i.start FROM idea i WHERE i.id = h.idea_id),
            (SELECT l.start FROM location l WHERE l.id = h.location_id),
            (SELECT min(p.start) FROM character_parameter p))
        WHERE h.start IS NULL
    """)
    op.execute("""
        UPDATE character_relation r SET start = GREATEST(
            (SELECT min(p.start) FROM character_parameter p WHERE p.character_id = r.character_1_id),
            (SELECT min(p.start) FROM character_parameter p WHERE p.character_id = r.character_2_id))
        WHERE r.start IS NULL
    """)
    op.execute(f"""
        UPDATE character_history_knower k SET start = COALESCE(
            (SELECT min(p.start) FROM character_parameter p WHERE p.character_id = k.knower_id),
            (SELECT {_YEAR_START.format(year='h.start')} FROM character_history h WHERE h.id = k.character_history_id),
            (SELECT l.start FROM location l WHERE l.id = k.location_id))
        WHERE k.start IS NULL
    """)
    op.execute(f"""
        UPDATE character_skill_history_knower k SET start = COALESCE(
            (SELECT min(p.start) FROM character_parameter p WHERE p.character_id = k.knower_id),
            (SELECT {_YEAR_START.format(year='h.start')} FROM character_skill_history h
             WHERE h.id = k.character_skill_history_id),
            (SELECT l.start FROM location l WHERE l.id = k.location_id))
        WHERE k.start IS NULL
    """)
    op.execute("""
        UPDATE idea_history_knower k SET start = COALESCE(
            (SELECT min(p.start) FROM character_parameter p WHERE p.character_id = k.knower_id),
            (SELECT h.start FROM idea_history h WHERE h.id = k.idea_history_id),
            (SELECT l.start FROM location l WHERE l.id = k.location_id))
        WHERE k.start IS NULL
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # 埋めた時刻は、もとから入っていた時刻と見分けられないので戻さない
    _set_comment(_OLD_COMMENT, _NEW_COMMENT)
