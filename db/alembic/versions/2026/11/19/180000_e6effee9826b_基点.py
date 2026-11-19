"""基点

これより前のマイグレーションをまとめた基点。表はこの版の `db/schema.py` のとおりで、空の db は `db.postgres.init_db` で作り、
この版を付ける。版の id は、まとめる前の最後の版と同じにしてあるので、その版にいる db は付け替えずにここから上げられる。

Revision ID: e6effee9826b
Revises:
Create Date: 2026-11-19 18:00:00

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'e6effee9826b'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
