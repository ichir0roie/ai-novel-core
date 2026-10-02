"""人物の来歴は、年ごとの行(`character_history`)を時刻で絞って読む。人物の芯は `Character.text` に持つ。"""
from typing import Any

from data_access_logic.character.record import CharacterHistoryRow
from data_access_logic.source_text import plot_section
from db.schema import Character, CharacterHistory
from db.stamp import Stamp


def _start(row: CharacterHistory) -> float:
    return row.start if row.start is not None else float("inf")


def histories_at(character: Character, time: Stamp | None) -> list[CharacterHistoryRow]:
    """時刻の年までに始まった行を、始まりの古い順に返す。時刻が空ならすべての行(作者が読むとき。年未定の行は最後)。

    時刻より後に始まる行と、年の決まっていない行を外すので、先のことを書き足しても、それより前の話・出来事には効かない。
    """
    rows = [row for row in character.histories if time is None or row.covers(time)]
    return [CharacterHistoryRow.model_validate(row) for row in sorted(rows, key=_start)]


def add_history(character: Character, year: int, description: str) -> None:
    """その年の行があれば、その説明に一文を書き足す(行を増やしすぎない)。無ければ、その年から始まる行を足す。"""
    row = next((row for row in character.histories if row.start == year), None)
    if row is None:
        character.histories.append(CharacterHistory(start=year, description=description))
    else:
        row.description = f"{row.description}\n{description}"


def plot_of(character: Character) -> str:
    """芯(`text`)の `# plot` の節(その人物について進めたい筋書き)。"""
    return plot_section(character.text or "")


def histories_for_prompt(histories: list[CharacterHistoryRow]) -> list[dict[str, Any]]:
    return [{"年": history.start, "来歴": history.description} for history in histories]
