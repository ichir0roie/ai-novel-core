"""人物の名字・体格・口調・性格は、変わった時ごとの行(`character_parameter`)を重ねて決める。"""

import logging
from collections import Counter

from pydantic import BaseModel

from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.character.record import CharacterParameterRow
from db.schema import Character, CharacterParameter
from db.stamp import Stamp

logger = logging.getLogger(__name__)


def _order(row: CharacterParameter) -> tuple:
    # 始まりの遅い行ほど後に重ねて勝たせる。同じなら後に足した行が勝つ
    return row.start.to_int() if row.start is not None else -1, row.id or 0


def overlay(values: CharacterParameterValues, row: BaseModel) -> None:
    """`row` の空でない値で `values` を上書きする。`row` の期間(start・end)は値ではないので見ない。"""
    for name, value in row:
        if value is not None and name in CharacterParameterValues.model_fields:
            setattr(values, name, value)


def parameters_at(character: Character, time: Stamp | None) -> CharacterParameterValues:
    """時刻までに始まった行を、始まりの古い順に重ねる。どの行も決めていない性格の軸は「並」。
    時刻が空なら、始まりの無い行と一番早く始まる行(誕生の行)だけ、つまり生まれたときの値。"""
    rows = list(character.parameters)
    if time is None:
        born = character.start
        selected = [row for row in rows if row.start is None or row.start == born]
    else:
        selected = [row for row in rows if row.covers(time)]
    values = CharacterParameterValues()
    for row in sorted(selected, key=_order):
        overlay(values, CharacterParameterRow.model_validate(row))
    return values


def parameter_row(values: CharacterParameterValues, start: Stamp | None) -> CharacterParameter:
    row = CharacterParameter(start=start)
    for name, value in values:
        setattr(row, name, value)
    return row


def warn_same_starts(character: Character) -> None:
    """始まりの同じ行が幾つもあれば知らせる(後の行が勝つので動きはするが、どちらの値が効くかが読み取りにくい)。"""
    counts = Counter(Stamp.parse(row.start) for row in character.parameters)
    same = [str(start) if start is not None else "空" for start, count in counts.items() if count > 1]
    if same:
        logger.warning(f"人物 id={character.id} のパラメータに、始まりの同じ行がある: {', '.join(same)}")
