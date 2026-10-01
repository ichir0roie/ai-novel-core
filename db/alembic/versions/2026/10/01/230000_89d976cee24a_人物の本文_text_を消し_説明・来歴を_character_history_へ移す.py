"""人物の本文(text)を消し、説明・来歴を character_history へ移す

先の時刻の来歴を書き足しても、それより前の話・出来事に効かないよう、人物の説明・来歴は期間ごとの行だけで持つ。
本文の `# 来歴` の節の `- <年>年(<歳>歳): …` の行は、その年から始まる行に一件ずつ移し、
残り(説明・`# meme`・`# 行動原理`・`# plot` など)は期間を限らない一行にまとめる。

Revision ID: 89d976cee24a
Revises: 4b7e2c91d0a3
Create Date: 2026-10-01 23:00:00.000000

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.stamp import Stamp


# revision identifiers, used by Alembic.
revision: str = '89d976cee24a'
down_revision: Union[str, Sequence[str], None] = '4b7e2c91d0a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

HISTORY_HEADING = "# 来歴"
_HEADING = re.compile(r"^#[ \t]")
_HISTORY_HEADING = re.compile(r"^#[ \t]*来歴[ \t]*$")
_HISTORY_LINE = re.compile(r"^[-*・][ \t]*(\d+)[ \t]*年(?:[(\uff08][^)\uff09]*[)\uff09])?[ \t]*[:\uff1a][ \t]*(.+?)[ \t]*$")

_character = sa.table("character", sa.column("id", sa.Integer), sa.column("text", sa.String))
_history = sa.table(
    "character_history",
    sa.column("id", sa.Integer), sa.column("character_id", sa.Integer),
    sa.column("start", sa.BigInteger), sa.column("end", sa.BigInteger), sa.column("description", sa.String))


def split_text(text: str) -> tuple[str, list[tuple[int, str]]]:
    """本文を、期間を限らない芯と、`# 来歴` の節の年の付いた行(年, 説明)に分ける。
    年の読めない行は芯の `# 来歴` の節に残す(読める行だけなら節ごと芯から外す)。"""
    core: list[str] = []
    dated: list[tuple[int, str]] = []
    heading_at: int | None = None
    kept = False
    for line in text.splitlines():
        if _HEADING.match(line):
            if heading_at is not None and not kept:
                del core[heading_at:]
            heading_at, kept = (len(core), False) if _HISTORY_HEADING.match(line.strip()) else (None, False)
        elif heading_at is not None:
            match = _HISTORY_LINE.match(line.strip())
            if match:
                dated.append((int(match.group(1)), match.group(2)))
                continue
            kept = kept or bool(line.strip())
        core.append(line)
    if heading_at is not None and not kept:
        del core[heading_at:]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(core)).strip(), dated


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    rows = conn.execute(sa.select(_character.c.id, _character.c.text).order_by(_character.c.id)).fetchall()
    for character_id, text in rows:
        core, dated = split_text(text or "")
        values = [{"character_id": character_id, "start": None, "end": None, "description": core}] if core else []
        values += [{"character_id": character_id, "start": Stamp(year).to_int(), "end": None, "description": description}
                   for year, description in dated]
        if values:
            conn.execute(sa.insert(_history), values)

    with op.batch_alter_table('character', schema=None) as batch_op:
        batch_op.drop_column('text')


def downgrade() -> None:
    """Downgrade schema.

    期間を限らない行と、終わりの無い行を本文へ畳み戻し(始まりのある行は `# 来歴` の節の行にする)、畳んだ行は消す。
    """
    with op.batch_alter_table('character', schema=None) as batch_op:
        batch_op.add_column(sa.Column('text', sa.String(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.select(_history.c.id, _history.c.character_id, _history.c.start, _history.c.description)
        .where(_history.c.end.is_(None))
        .order_by(_history.c.character_id, _history.c.start.asc().nulls_first(), _history.c.id)).fetchall()
    by_character: dict[int, tuple[list[str], list[str], list[int]]] = {}
    for history_id, character_id, start, description in rows:
        core, dated, ids = by_character.setdefault(character_id, ([], [], []))
        if start is None:
            core.append(description)
        else:
            # 台帳の時刻の整数は 年*10^10 + 月*10^8 + …(db/stamp.py)
            dated.append(f"- {start // 10 ** 10}年: {description}")
        ids.append(history_id)
    for character_id, (core, dated, ids) in by_character.items():
        blocks = [*core, f"{HISTORY_HEADING}\n" + "\n".join(dated)] if dated else core
        conn.execute(sa.update(_character).where(_character.c.id == character_id).values(text="\n\n".join(blocks)))
        conn.execute(sa.delete(_history).where(_history.c.id.in_(ids)))
