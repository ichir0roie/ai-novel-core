"""flag・参照の列に仕様の comment を足す

Revision ID: 5b2e7c9a1d34
Revises: 8f3a6d2c41b7
Create Date: 2026-10-04 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b2e7c9a1d34'
down_revision: Union[str, Sequence[str], None] = '8f3a6d2c41b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('location', 'parent_id', existing_type=sa.INTEGER(), existing_nullable=True,
                    comment='一つ上の場所。断面・知る相手・アイデアの効く場所は、この木をたどって配下の場所まで含む', existing_comment=None)
    op.alter_column('location', 'active_random_generation', existing_type=sa.BOOLEAN(), existing_nullable=False,
                    comment='ランダム生成の対象にするか。出来事の生成で新設された子の場所は親の値を継ぐ。場所を名指しする出来事の生成(GenerateEvent)はこの値を見ない', existing_comment=None)
    op.alter_column('event', 'hidden', existing_type=sa.BOOLEAN(), existing_nullable=False,
                    comment='場所の断面(ReadBrief)に出さないか。true なら full で読むときだけ出す。分類は持たず、name・text の書き方で表す', existing_comment=None)
    op.alter_column('event', 'parent_event_id', existing_type=sa.INTEGER(), existing_nullable=True,
                    comment='上位の出来事(この出来事を含む大きな出来事)', existing_comment=None)
    op.alter_column('event', 'location_id', existing_type=sa.INTEGER(), existing_nullable=True,
                    comment='起きた場所。場所の断面(ReadBrief)は、その場所と配下で起きた出来事を読む', existing_comment=None)
    op.alter_column('character_location', 'location_id', existing_type=sa.INTEGER(), existing_nullable=False,
                    comment='住まい・拠点にする場所', existing_comment=None)
    op.alter_column('character_location', 'start', existing_type=sa.BIGINT(), existing_nullable=True,
                    comment='住み始めた時刻。空なら初めから', existing_comment=None)
    op.alter_column('character_location', 'end', existing_type=sa.BIGINT(), existing_nullable=True,
                    comment='離れた時刻(この時刻からはいない)。空ならまだいる', existing_comment=None)
    op.alter_column('episode', 'story_id', existing_type=sa.INTEGER(), existing_nullable=False,
                    comment='属する作品。章の話は章の作品に付け、書くときは親の作品の筋書きまでたどる', existing_comment=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('location', 'parent_id', existing_type=sa.INTEGER(), existing_nullable=True,
                    comment=None, existing_comment='一つ上の場所。断面・知る相手・アイデアの効く場所は、この木をたどって配下の場所まで含む')
    op.alter_column('location', 'active_random_generation', existing_type=sa.BOOLEAN(), existing_nullable=False,
                    comment=None, existing_comment='ランダム生成の対象にするか。出来事の生成で新設された子の場所は親の値を継ぐ。場所を名指しする出来事の生成(GenerateEvent)はこの値を見ない')
    op.alter_column('event', 'hidden', existing_type=sa.BOOLEAN(), existing_nullable=False,
                    comment=None, existing_comment='場所の断面(ReadBrief)に出さないか。true なら full で読むときだけ出す。分類は持たず、name・text の書き方で表す')
    op.alter_column('event', 'parent_event_id', existing_type=sa.INTEGER(), existing_nullable=True,
                    comment=None, existing_comment='上位の出来事(この出来事を含む大きな出来事)')
    op.alter_column('event', 'location_id', existing_type=sa.INTEGER(), existing_nullable=True,
                    comment=None, existing_comment='起きた場所。場所の断面(ReadBrief)は、その場所と配下で起きた出来事を読む')
    op.alter_column('character_location', 'location_id', existing_type=sa.INTEGER(), existing_nullable=False,
                    comment=None, existing_comment='住まい・拠点にする場所')
    op.alter_column('character_location', 'start', existing_type=sa.BIGINT(), existing_nullable=True,
                    comment=None, existing_comment='住み始めた時刻。空なら初めから')
    op.alter_column('character_location', 'end', existing_type=sa.BIGINT(), existing_nullable=True,
                    comment=None, existing_comment='離れた時刻(この時刻からはいない)。空ならまだいる')
    op.alter_column('episode', 'story_id', existing_type=sa.INTEGER(), existing_nullable=False,
                    comment=None, existing_comment='属する作品。章の話は章の作品に付け、書くときは親の作品の筋書きまでたどる')
