"""装いを人物の来歴へ移し、来歴に種別を足す

装いを変えるたびに人物のパラメータ(`character_parameter`)の行が増えるので、装いの列(`outfit`)を消し、
人物の来歴(`character_history`)に種別(`kind`)を足して、装い・持ち物・記憶・隠し事も来歴の行で持つ。

- 装いの値が変わったパラメータの行ごとに、種別「装い」の来歴の行を足す。始まりはその行の始まり(空なら誕生。誕生も
  空なら空)。知る相手は本人(誕生から)。その時刻の一番新しい装いの行は、知る相手に関わらず見た目として渡る
- 装いを抜いたあと、どの時刻の値も変えない行(空の行・前の行と同じ値だけを持つ行)を消す。誕生を表す、一番早く始まる行は残す

Revision ID: 4e0b659755e4
Revises: 5041301983c8
Create Date: 2026-10-18 23:22:43.369439

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e0b659755e4'
down_revision: Union[str, Sequence[str], None] = '5041301983c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OUTFIT_KIND = "装い"
# 装いのほかに、パラメータの行が持つ値の列(`db/schema.py` の `CharacterParameter`)
VALUE_COLUMNS = (
    "family_name", "sex", "height", "build", "first_person", "second_person", "third_person", "tone", "dialect",
    "sincerity", "curiosity", "proactivity", "cooperativeness", "sociability", "emotional_expression", "self_esteem",
    "self_efficacy", "stress_resilience", "flexibility_of_values", "sensitivity", "imagination",
)

_parameter = sa.table(
    "character_parameter", sa.column("id", sa.Integer), sa.column("character_id", sa.Integer),
    sa.column("start", sa.BigInteger), sa.column("outfit", sa.String), *(sa.column(name) for name in VALUE_COLUMNS))
_history = sa.table(
    "character_history", sa.column("id", sa.Integer), sa.column("character_id", sa.Integer),
    sa.column("start", sa.BigInteger), sa.column("kind", sa.String), sa.column("description", sa.String))
_knower = sa.table(
    "character_history_knower", sa.column("character_history_id", sa.Integer), sa.column("knower_id", sa.Integer),
    sa.column("location_id", sa.Integer), sa.column("start", sa.BigInteger))


def _ordered(rows: list) -> list:
    # `data_access_logic/character/parameters.py` の重ねる順(始まりの空な行が先、同じなら id の順)
    return sorted(rows, key=lambda row: (-1 if row.start is None else row.start, row.id))


def _move_outfits(conn, character_id: int, rows: list, birth: int | None) -> None:
    worn = None
    for row in _ordered(rows):
        if row.outfit is None or row.outfit == worn:
            continue
        worn = row.outfit
        start = row.start if row.start is not None else birth
        history_id = conn.execute(sa.insert(_history).values(
            character_id=character_id, start=start, kind=OUTFIT_KIND, description=row.outfit,
        ).returning(_history.c.id)).scalar_one()
        conn.execute(sa.insert(_knower).values(
            character_history_id=history_id, knower_id=character_id, location_id=None, start=birth))


def _idle_rows(rows: list, birth: int | None) -> list[int]:
    """どの時刻の値も変えない行の id。誕生の行(一番早く始まる行のうち先のもの)は残す。"""
    birth_row = next((row for row in _ordered(rows) if birth is not None and row.start == birth), None)
    values: dict[str, object] = {}
    idle = []
    for row in _ordered(rows):
        decided = {name: getattr(row, name) for name in VALUE_COLUMNS if getattr(row, name) is not None}
        if row is not birth_row and all(values.get(name) == value for name, value in decided.items()):
            idle.append(row.id)
            continue
        values.update(decided)
    return idle


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('character_history', sa.Column('kind', sa.String(), nullable=True, comment='種別(装い・持ち物・記憶・隠し事など)。空なら起きた出来事'))

    conn = op.get_bind()
    by_character: dict[int, list] = {}
    for row in conn.execute(sa.select(_parameter)).fetchall():
        by_character.setdefault(row.character_id, []).append(row)
    for character_id, rows in by_character.items():
        starts = [row.start for row in rows if row.start is not None]
        birth = min(starts) if starts else None
        _move_outfits(conn, character_id, rows, birth)
        idle = _idle_rows(rows, birth)
        if idle:
            conn.execute(sa.delete(_parameter).where(_parameter.c.id.in_(idle)))

    op.drop_column('character_parameter', 'outfit')


def downgrade() -> None:
    """Downgrade schema.

    種別「装い」の来歴の行を、同じ始まりのパラメータの行の装いへ戻し(無ければその始まりの行を足す)、来歴の行は消す。
    消したパラメータの行はどの時刻の値も変えなかったので戻さない。ほかの種別の行は、種別を外した来歴として残る。
    """
    op.add_column('character_parameter', sa.Column('outfit', sa.VARCHAR(), autoincrement=False, nullable=True, comment='装い。身なりと、人目に見える持ち物・武器・傷・印'))

    conn = op.get_bind()
    outfits = conn.execute(
        sa.select(_history.c.id, _history.c.character_id, _history.c.start, _history.c.description)
        .where(_history.c.kind == OUTFIT_KIND).order_by(_history.c.id)).fetchall()
    for history_id, character_id, start, description in outfits:
        same_start = _parameter.c.start.is_(None) if start is None else _parameter.c.start == start
        parameter_id = conn.execute(
            sa.select(_parameter.c.id).where(_parameter.c.character_id == character_id, same_start)
            .order_by(_parameter.c.id.desc()).limit(1)).scalar()
        if parameter_id is None:
            conn.execute(sa.insert(_parameter).values(character_id=character_id, start=start, outfit=description))
        else:
            conn.execute(sa.update(_parameter).where(_parameter.c.id == parameter_id).values(outfit=description))
        conn.execute(sa.delete(_knower).where(_knower.c.character_history_id == history_id))
        conn.execute(sa.delete(_history).where(_history.c.id == history_id))

    op.drop_column('character_history', 'kind')
