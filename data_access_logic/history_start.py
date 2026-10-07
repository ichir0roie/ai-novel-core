"""来歴の行(人物・スキル・関係・場所)の始まり(`start`)の扱い。始まりは出来事の時刻で、空なら時期が決まっていない。"""
from typing import Any

from db.stamp import Stamp


def by_start(row: Any) -> tuple[bool, int]:
    """来歴の行を、始まりの古い順に並べる鍵。時期の決まっていない行は最後。"""
    return (row.start is None, row.start.to_int() if row.start is not None else 0)


def start_for_prompt(start: Stamp | None) -> str | None:
    """来歴の始まりを、AI に渡す日付にする(時分秒は来歴に要らない)。"""
    return None if start is None else f"{start.year}/{start.month:02d}/{start.day:02d}"
