"""来歴の始まりを時刻に

人物・スキル・関係・場所の来歴(`character_history`・`character_skill_history`・`character_relation_history`・
`location_history`)の `start` を、年の整数から時刻(`StampType`。`年*10^10 + 月*10^8 + … + 秒` の整数)に変える。
年単位だと、同じ年の後の出来事が前の時刻の話に漏れ、知る相手も年でまとめてしまうため、出来事ごとの時刻で持つ。
既にある行は、その年の 1 月 1 日にする(年の頭から効くので、今までと同じ時刻の話に渡る)。

Revision ID: b7c3e9a10f42
Revises: a1b45d45dd36
Create Date: 2026-10-07 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c3e9a10f42'
down_revision: Union[str, Sequence[str], None] = 'a1b45d45dd36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (表, 空の行を話のどちらに渡さないか)
TABLES = (
    ('character_history', '話・出来事'),
    ('location_history', '話・出来事'),
    ('character_skill_history', '話・人物役'),
    ('character_relation_history', '話・人物役'),
)
# 年の下の 月・日・時・分・秒 の桁。1 月 1 日 0 時 0 分 0 秒
YEAR = 10 ** 10
JANUARY_FIRST = 1 * 10 ** 8 + 1 * 10 ** 6


def upgrade() -> None:
    """Upgrade schema."""
    for table, readers in TABLES:
        op.alter_column(
            table, 'start', type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=True,
            postgresql_using=f'start::bigint * {YEAR} + {JANUARY_FIRST}',
            comment=f'起きた時刻(この来歴が効き始める時刻)。空なら時期が決まっていない({readers}には渡さない)',
            existing_comment=f'起きた年(この来歴が効き始める年)。空なら年が決まっていない({readers}には渡さない)')


def downgrade() -> None:
    """Downgrade schema."""
    for table, readers in TABLES:
        op.alter_column(
            table, 'start', type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=True,
            postgresql_using=f'(start / {YEAR})::integer',
            comment=f'起きた年(この来歴が効き始める年)。空なら年が決まっていない({readers}には渡さない)',
            existing_comment=f'起きた時刻(この来歴が効き始める時刻)。空なら時期が決まっていない({readers}には渡さない)')
