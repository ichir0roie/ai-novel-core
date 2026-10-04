"""人物の来歴は、年ごとの行(`character_history`)を時刻で絞って読む。人物の芯は `Character.text` に持つ。"""
from typing import Any

from data_access_logic.character.record import CharacterHistoryRow
from db.schema import Character, CharacterHistory, CharacterHistoryKnower
from db.stamp import Stamp


def _start(row: CharacterHistory) -> float:
    return row.start if row.start is not None else float("inf")


def rows_at(character: Character, time: Stamp | None) -> list[CharacterHistory]:
    """時刻の年までに始まった行を、始まりの古い順に返す。時刻が空ならすべての行(作者が読むとき。年未定の行は最後)。

    時刻より後に始まる行と、年の決まっていない行を外すので、先のことを書き足しても、それより前の話・出来事には効かない。
    """
    rows = [row for row in character.histories if time is None or row.covers(time)]
    return sorted(rows, key=_start)


def histories_at(character: Character, time: Stamp | None) -> list[CharacterHistoryRow]:
    return [CharacterHistoryRow.model_validate(row) for row in rows_at(character, time)]


def _known_only_by(row: CharacterHistory, character: Character) -> bool:
    return row.private and len(row.knowers) == 1 and row.knowers[0].start is None and (
        row.knowers[0].knower is character or (character.id is not None and row.knowers[0].knower_id == character.id))


def add_history(character: Character, year: int, description: str) -> None:
    """その年の、本人だけが知る非公開の行があれば、その説明に一文を書き足す(行を増やしすぎない)。無ければ、その年から始まり
    本人だけが知る非公開の行を足す(ほかの人も知る行に書き足すと、本人しか知らないはずのことが広まる)。"""
    row = next((row for row in character.histories if row.start == year and _known_only_by(row, character)), None)
    if row is None:
        character.histories.append(CharacterHistory(
            start=year, description=description, private=True, knowers=[CharacterHistoryKnower(knower=character)]))
    else:
        row.description = f"{row.description}\n{description}"


def histories_for_prompt(histories: list[CharacterHistoryRow]) -> list[dict[str, Any]]:
    return [{"年": history.start, "来歴": history.description} for history in histories]
