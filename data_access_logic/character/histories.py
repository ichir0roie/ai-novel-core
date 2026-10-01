"""人物の説明・来歴は、期間ごとの行(`character_history`)を時刻で絞って読む。"""
from typing import Any

from data_access_logic.character.record import CharacterHistoryRow
from data_access_logic.source_text import plot_section
from db.schema import Character, CharacterHistory
from db.stamp import Stamp


def _start(row: CharacterHistory) -> int:
    return row.start.to_int() if row.start is not None else -1


def histories_at(character: Character, time: Stamp | None) -> list[CharacterHistoryRow]:
    """時刻までに始まった行を、始まりの古い順に返す。時刻が空ならすべての行(作者が読むとき)。

    時刻より後に始まる行を外すので、先のことを書き足しても、それより前の話・出来事には効かない。
    """
    rows = [row for row in character.histories if time is None or row.covers(time)]
    return [CharacterHistoryRow.model_validate(row) for row in sorted(rows, key=_start)]


def plot_of(character: Character) -> str:
    """各行の `# plot` の節(その人物について進めたい筋書き)。"""
    sections = (plot_section(row.description) for row in sorted(character.histories, key=_start))
    return "\n\n".join(section for section in sections if section)


def histories_for_prompt(histories: list[CharacterHistoryRow]) -> list[dict[str, Any]]:
    return [{"いつから": str(history.start) if history.start else None, "説明": history.description}
            for history in histories]
