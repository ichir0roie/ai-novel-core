"""アイデア本体の効く期間を履歴の行へ移す

Revision ID: d97f678fc077
Revises: 57b0b8a7ff35
Create Date: 2026-10-20 03:51:55.143119

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd97f678fc077'
down_revision: Union[str, Sequence[str], None] = '57b0b8a7ff35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # これまで効く期間は、本体の期間と履歴の行の期間が重なる所だった。その重なりを履歴の行へ移す
    op.execute(sa.text("""
        UPDATE idea_history AS h
        SET start = CASE WHEN i.start IS NULL THEN h.start ELSE GREATEST(COALESCE(h.start, i.start), i.start) END,
            "end" = CASE WHEN i."end" IS NULL THEN h."end" ELSE LEAST(COALESCE(h."end", i."end"), i."end") END
        FROM idea AS i
        WHERE h.idea_id = i.id AND (i.start IS NOT NULL OR i."end" IS NOT NULL)
    """))
    # 履歴の行の無いアイデアは本体の期間だけで効いていたので、どこでも効く行にして移す
    op.execute(sa.text("""
        INSERT INTO idea_history (idea_id, location_id, start, "end", name)
        SELECT i.id, NULL, i.start, i."end", i.name
        FROM idea AS i
        WHERE (i.start IS NOT NULL OR i."end" IS NOT NULL)
          AND NOT EXISTS (SELECT 1 FROM idea_history AS h WHERE h.idea_id = i.id)
    """))
    op.drop_column('idea', 'end')
    op.drop_column('idea', 'start')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('idea', sa.Column('start', sa.BIGINT(), autoincrement=False, nullable=True, comment='効き始める時刻。出来事の時刻と比べる。空なら始まりを限らない'))
    op.add_column('idea', sa.Column('end', sa.BIGINT(), autoincrement=False, nullable=True, comment='効き終わる時刻(この時刻からは効かない)。空なら終わりを限らない'))
    # 履歴の行へ移した期間は分けられないので、始まりだけを一番早い行から戻す
    op.execute(sa.text("""
        UPDATE idea SET start = (SELECT MIN(h.start) FROM idea_history AS h WHERE h.idea_id = idea.id)
    """))
