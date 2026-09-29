"""人物の名字・体格・口調・性格は、期間ごとの行(`character_parameter`)を重ねて決める。"""
import random

from pydantic import BaseModel

from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.character.record import CharacterParameterRow
from db.schema import PERSON_PARAMETER_COLUMNS, PERSONALITY_COLUMNS, Character, CharacterParameter, PersonalityLevel
from db.stamp import Stamp

_HEIGHT_RANGE_CM = (140.0, 195.0)


def _bounds(row: CharacterParameter) -> int:
    return (row.start is not None) + (row.end is not None)


def _order(row: CharacterParameter) -> tuple:
    # 期間を限る端が多い行ほど後に重ねて勝たせる。同じなら始まりの遅い行、後に足した行が勝つ
    return _bounds(row), row.start.to_int() if row.start is not None else -1, row.id or 0


def overlay(values: CharacterParameterValues, row: BaseModel) -> None:
    """`row` の空でない値で `values` を上書きする。`row` の期間(start・end)は値ではないので見ない。"""
    for name, value in row:
        if value is not None and name in CharacterParameterValues.model_fields:
            setattr(values, name, value)


def parameters_at(character: Character, time: Stamp | None) -> CharacterParameterValues:
    """時刻に掛かる行を、期間を限らない行から順に重ねる。どの行も決めていない性格の軸は「並」。"""
    rows = list(character.parameters)
    if time is None:
        # 一番早く始まる行の start は誕生(`Character.start`)を、一番後に始まる行の end は
        # 死亡(`Character.end`)を兼ねるので、`covers(None)`(期間を限らない行だけ)に絞ると、
        # 誕生・死亡を持つだけの行(たいていは唯一の行)まで丸ごと外れてしまう。
        # 代わりに、一番限る端が少ない(＝一番土台になる)行を採る。
        least = min((_bounds(row) for row in rows), default=None)
        selected = [row for row in rows if _bounds(row) == least]
    else:
        selected = [row for row in rows if row.covers(time)]
    values = CharacterParameterValues()
    for row in sorted(selected, key=_order):
        overlay(values, CharacterParameterRow.model_validate(row))
    return values


def rolled(rng: random.Random) -> CharacterParameterValues:
    """名字・性別・体格・口調は少ない候補から引くと偏るので、ここでは決めずに AI に人物説明と合わせて決めさせる。"""
    values = CharacterParameterValues(height=round(rng.uniform(*_HEIGHT_RANGE_CM), 1))
    for name in PERSONALITY_COLUMNS:
        setattr(values, name, rng.choice(list(PersonalityLevel)))
    return values


def without_person_values(values: CharacterParameterValues) -> CharacterParameterValues:
    """人物以外の対象は、名字・体格・口調を持たない。"""
    for name in PERSON_PARAMETER_COLUMNS:
        setattr(values, name, None)
    return values


def parameter_row(values: CharacterParameterValues, start: Stamp | None, end: Stamp | None) -> CharacterParameter:
    row = CharacterParameter(start=start, end=end)
    for name, value in values:
        setattr(row, name, value)
    return row
