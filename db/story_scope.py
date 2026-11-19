#!/usr/bin/env python3
"""呼び出しの文脈の作品と、時刻を数える暦。

入口・段・画面の API は、引数や開いた行から作品と暦を決めてここに立てる(`data_access_logic/story/scope.py`)。暦は、
引数や開いた行の持ち主の行の暦で、行が無ければ作品の暦(新しい行の既定)。立てた暦で時刻を数え(`db/stamp.py`)、
足した人物・アイデア・場所に作品が無ければこの作品を、足した持ち主の行に暦が無ければこの暦を入れる(`db/schema.py`)。
web のセッションは db に繋がないので、作品と暦を API へヘッダ(`STORY_HEADER`・`CUSTOM_STAMP_HEADER`)で運ぶ。
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from db.stamp import Calendar, set_calendar, using_calendar

STORY_HEADER = "x-novel-story"
CUSTOM_STAMP_HEADER = "x-novel-custom-stamp"
# 作品を決めたうえで、どの作品にも当たらない(西暦で数える)ことをヘッダで言う値
NO_STORY = "none"


@dataclass(frozen=True)
class Scope:
    story_id: int | None = None
    # 暦の行の id と、その暦(西暦なら None)
    custom_stamp_id: int | None = None
    calendar: Calendar | None = None


# None なら、まだだれも作品を決めていない(決めて作品が無いときは `Scope()`)
_scope: ContextVar[Scope | None] = ContextVar("story_scope", default=None)


def current() -> Scope | None:
    return _scope.get()


def current_story_id() -> int | None:
    scope = _scope.get()
    return None if scope is None else scope.story_id


@contextmanager
def scoped(scope: Scope) -> Iterator[Scope]:
    token = _scope.set(scope)
    try:
        with using_calendar(scope.calendar):
            yield scope
    finally:
        _scope.reset(token)


def adopt(scope: Scope) -> None:
    """今の文脈に作品を立てたままにする(web のセッションが、API から受けた作品と暦をこの先の流れに使う)。"""
    _scope.set(scope)
    set_calendar(scope.calendar)


def headers() -> dict[str, str]:
    """API に運ぶヘッダ。作品を決めていれば、作品が無いことも運ぶ(段を流れの作品のまま回してもらうため)。"""
    scope = current()
    if scope is None:
        return {}
    found = {STORY_HEADER: NO_STORY if scope.story_id is None else str(scope.story_id)}
    if scope.custom_stamp_id is not None:
        found[CUSTOM_STAMP_HEADER] = str(scope.custom_stamp_id)
    return found


def scope_in_headers(values: Mapping[str, str]) -> bool:
    """呼ぶ側が作品を決めて運んだか(作品が無いと決めたときも)。"""
    return STORY_HEADER in values


def story_from_headers(values: Mapping[str, str]) -> int | None:
    raw = values.get(STORY_HEADER, "").strip()
    return int(raw) if raw.isdigit() else None


def custom_stamp_from_headers(values: Mapping[str, str]) -> int | None:
    raw = values.get(CUSTOM_STAMP_HEADER, "").strip()
    return int(raw) if raw.isdigit() else None
