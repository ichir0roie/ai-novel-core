#!/usr/bin/env python3
"""呼び出しの作品と暦を決めて、文脈に立てる(`db/story_scope.py`)。

作品と暦は、入口・段の引数(`story_id`・`episode_id` など、行を指す欄)か、画面で開いた行から決める。引数では、書く行そのもの
(来歴の `history_id`、`table` と `row_id`、行をまるごと渡す欄の `id`)を先に見て、そのあと浅い欄から深い欄へ、行を指す欄を見る
(来歴の知る相手のような入れ子の欄で、書く行と別の作品に決まらないように)。人物・アイデア・場所は自分の作品を持ち、
来歴などの子の行は親の行の作品、出来事は場所・当事者・上位の出来事の作品に従う。
暦は、持ち主の行(話・出来事・人物・アイデア・場所・関係)の `custom_stamp_id` の暦で、来歴などの子の行は持ち主の暦。
引数から行が決まらなければ、作品の `custom_stamp_id`(新しい行の既定)の暦。
"""
from __future__ import annotations

import re
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from db import story_scope
from db.schema import (
    Base, Character, CharacterHistory, CharacterLocation, CharacterMotivation, CharacterNuance, CharacterRelation,
    CharacterRelationHistory,
    CharacterSkill, CharacterSkillHistory, CustomStamp, CustomStampMonth, Episode, Event, EventCharacter, Expansion, Idea,
    IdeaHistory, Location, LocationHistory, Story, get_env_session,
)
from db.stamp import Calendar
from db.story_scope import Scope

# 行を指す欄のうち、表の名前と頭の合わないもの。ほかは `<表>_id` / `<表>_ids` の名前から表を引く
_KEY_MODELS: dict[str, type[Base]] = {
    "actor_id": Character, "knower_id": Character, "character_1_id": Character, "character_2_id": Character,
    "viewpoint_character_id": Character, "around_character_id": Character,
}
_KEY_PATTERN = re.compile(r"\A(\w+?)_ids?\Z")
# 同じ深さに行を指す欄がいくつもあるとき、先に見る表(小さいほど作品・暦を確かに決める。無い表は 4)
_MODEL_RANKS: dict[type[Base], int] = {
    CustomStamp: -1, Story: 0, Episode: 1, Expansion: 2, Event: 3, Character: 5, Idea: 6, Location: 7}
# 入口の引数で、行をまるごと渡す欄(`{"character": {"id": 3, ...}}`)
_FORM_MODELS: dict[str, type[Base]] = {
    "story": Story, "episode": Episode, "event": Event, "character": Character, "idea": Idea, "location": Location,
    "relation": CharacterRelation, "skill": CharacterSkill, "motivation": CharacterMotivation, "nuance": CharacterNuance,
    "expansion": Expansion,
    "character_location": CharacterLocation,
}
# 来歴の行を `history_id` で指す入口の、来歴の表(入口のモジュール名から)
HISTORY_MODELS: dict[str, type[Base]] = {
    "character.update_history": CharacterHistory, "character.delete_history": CharacterHistory,
    "character.update_relation_history": CharacterRelationHistory,
    "character.delete_relation_history": CharacterRelationHistory,
    "character.update_skill_history": CharacterSkillHistory, "character.delete_skill_history": CharacterSkillHistory,
    "idea.update_history": IdeaHistory, "idea.delete_history": IdeaHistory,
    "location.update_history": LocationHistory, "location.delete_history": LocationHistory,
}
# 作品を持たない行がたどる親の行の表。分類の表(`personality_level` など)や作品の表そのものへは、たどらない
_OWNER_MODELS: frozenset[type[Base]] = frozenset({
    Character, CharacterHistory, CharacterRelation, CharacterSkill, CharacterSkillHistory, Episode, Event, Expansion,
    Idea, IdeaHistory, Location, LocationHistory,
})
_MAX_DEPTH = 12
# 暦は滅多に変わらないので、画面の一回の操作で何度も読まないよう少しだけ控える。暦の行を書いたら、その場で捨てる
# (`_forget_calendars`。ほかのプロセスの控えは、この長さのうちに切れる)
_CALENDAR_SECONDS = 10.0
_calendars: dict[int, tuple[float, Calendar | None]] = {}


@event.listens_for(Session, "after_flush")
def _forget_calendars(s: Session, _flush_context) -> None:
    if any(isinstance(row, (CustomStamp, CustomStampMonth)) for row in (*s.new, *s.dirty, *s.deleted)):
        _calendars.clear()


def calendar_of(s: Session, custom_stamp_id: int | None) -> Calendar | None:
    """暦の行の暦。西暦の行・空なら None。"""
    if custom_stamp_id is None:
        return None
    cached = _calendars.get(custom_stamp_id)
    if cached is not None and time.monotonic() - cached[0] < _CALENDAR_SECONDS:
        return cached[1]
    calendar = calendar_of_row(s.get_one(CustomStamp, custom_stamp_id))
    _calendars[custom_stamp_id] = (time.monotonic(), calendar)
    return calendar


def calendar_of_row(row: CustomStamp) -> Calendar | None:
    """暦の行の暦。月を持たない行(西暦)は None。"""
    if not row.months:
        return None
    return Calendar(offset=row.offset.western_digits, month_days=tuple(month.days for month in row.months),
                    hours_per_day=row.hours_per_day, days_per_week=row.days_per_week, name=row.name,
                    month_names=tuple(month.name or "" for month in row.months),
                    minutes_per_hour=row.minutes_per_hour, seconds_per_minute=row.seconds_per_minute,
                    outside_week_days=tuple(month.outside_week_days for month in row.months))


def custom_stamp_of_row(s: Session, model: type[Base], row_id: int | None, depth: int = 0) -> int | None:
    """行の暦の行の id。暦を持たない子の行は、持ち主の行(外部キーの先)の暦。"""
    if row_id is None or depth > _MAX_DEPTH:
        return None
    if model is CustomStamp:
        return row_id
    row = s.get(model, row_id)
    if row is None:
        return None
    if "custom_stamp_id" in model.__table__.columns:
        return getattr(row, "custom_stamp_id")
    for column in model.__table__.columns:
        for foreign_key in column.foreign_keys:
            target = model_of_table(foreign_key.column.table.name)
            if target not in _OWNER_MODELS:
                continue
            found = custom_stamp_of_row(s, target, getattr(row, column.key), depth + 1)
            if found is not None:
                return found
    return None


def story_of_row(s: Session, model: type[Base], row_id: int | None, depth: int = 0) -> int | None:
    """行の作品。作品を持たない行は、親の行(外部キーの先)の作品。"""
    if row_id is None or depth > _MAX_DEPTH:
        return None
    if model is Story:
        return row_id
    row = s.get(model, row_id)
    if row is None:
        return None
    story_id = getattr(row, "story_id", None)
    if story_id is not None:
        return story_id
    if model is Event:
        return _story_of_event(s, row, depth)
    for column in model.__table__.columns:
        for foreign_key in column.foreign_keys:
            target = model_of_table(foreign_key.column.table.name)
            if target not in _OWNER_MODELS:
                continue
            found = story_of_row(s, target, getattr(row, column.key), depth + 1)
            if found is not None:
                return found
    return None


def _story_of_event(s: Session, event: Event, depth: int) -> int | None:
    found = story_of_row(s, Location, event.location_id, depth + 1)
    if found is not None:
        return found
    for character_id in s.scalars(select(EventCharacter.character_id).where(EventCharacter.event_id == event.id)):
        found = story_of_row(s, Character, character_id, depth + 1)
        if found is not None:
            return found
    return story_of_row(s, Event, event.parent_event_id, depth + 1)


def model_of_table(name: str) -> type[Base] | None:
    for mapper in Base.registry.mappers:
        if mapper.class_.__tablename__ == name:
            return mapper.class_
    return None


def model_of_key(key: str) -> type[Base] | None:
    """行を指す欄(`character_id`・`location_ids` など)の表。行を指さない欄なら None。"""
    if key in _KEY_MODELS:
        return _KEY_MODELS[key]
    matched = _KEY_PATTERN.match(key)
    return None if matched is None else model_of_table(matched.group(1))


def _levels(args: Mapping[str, Any]) -> list[list[tuple[str, Any]]]:
    """欄の名前と値を、深さごとに分けて浅い順に並べる(配列の中の行は、配列と同じ深さに数える)。"""
    levels: list[list[tuple[str, Any]]] = []
    current: list[Mapping[str, Any]] = [args]
    while current:
        level = [(str(key), value) for mapping in current for key, value in mapping.items()]
        levels.append(level)
        current = [mapping for _, value in level for mapping in _mappings(value)]
    return levels


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, list):
        return [mapping for item in value for mapping in _mappings(item)]
    return []


def _rank(reference: tuple[type[Base], Any]) -> int:
    return _MODEL_RANKS.get(reference[0], 4)


def _ids(value: Any) -> list[int]:
    return [item for item in (value if isinstance(value, list) else [value]) if isinstance(item, int)]


def _rows_of_args(args: Mapping[str, Any], history_model: type[Base] | None) -> Iterator[tuple[type[Base], int]]:
    """引数が指す行を、作品・暦を決める順に。"""
    if history_model is not None and isinstance(args.get("history_id"), int):
        yield history_model, args["history_id"]
    table, row_id = args.get("table"), args.get("row_id")
    if isinstance(table, str) and isinstance(row_id, int) and (model := model_of_table(table)) is not None:
        yield model, row_id
    for level in _levels(args):
        for key, value in level:
            model = _FORM_MODELS.get(key)
            if model is not None and isinstance(value, Mapping) and isinstance(value.get("id"), int):
                yield model, value["id"]
        references: list[tuple[type[Base], Any]] = [
            (model, value) for key, value in level if (model := model_of_key(key)) is not None]
        references.sort(key=_rank)
        for model, value in references:
            for referred in _ids(value):
                yield model, referred


def story_of_args(s: Session, args: Mapping[str, Any], history_model: type[Base] | None = None) -> int | None:
    """入口・段の引数から作品を決める。決まらなければ None。"""
    for model, row_id in _rows_of_args(args, history_model):
        found = story_of_row(s, model, row_id)
        if found is not None:
            return found
    return None


def custom_stamp_of_args(s: Session, args: Mapping[str, Any], history_model: type[Base] | None = None) -> int | None:
    """入口・段の引数が指す行の暦の行の id。作品は暦の既定なので見ない(`scope_of` が埋める)。決まらなければ None。"""
    for model, row_id in _rows_of_args(args, history_model):
        if model is Story:
            continue
        found = custom_stamp_of_row(s, model, row_id)
        if found is not None:
            return found
    return None


def scope_of(s: Session, story_id: int | None, custom_stamp_id: int | None = None) -> Scope:
    """作品と暦の文脈。暦が決まっていなければ作品の暦(新しい行の既定)。"""
    if custom_stamp_id is None and story_id is not None:
        story = s.get(Story, story_id)
        custom_stamp_id = None if story is None else story.custom_stamp_id
    return Scope(story_id=story_id, custom_stamp_id=custom_stamp_id, calendar=calendar_of(s, custom_stamp_id))


@contextmanager
def story_scope_of(story_id: int | None, custom_stamp_id: int | None = None) -> Iterator[Scope]:
    with get_env_session() as s:
        scope = scope_of(s, story_id, custom_stamp_id)
    with story_scope.scoped(scope):
        yield scope


def args_scope_in(s: Session, args: Mapping[str, Any], fallback_story_id: int | None = None,
                  history_model: type[Base] | None = None) -> Scope:
    """引数から作品と暦を決める。作品が引数から決まらなければ `fallback_story_id`、それも無ければ今の文脈の作品と暦のまま。"""
    story_id = story_of_args(s, args, history_model)
    custom_stamp_id = custom_stamp_of_args(s, args, history_model)
    current = story_scope.current()
    if story_id is None and fallback_story_id is None and current is not None:
        return current if custom_stamp_id is None else scope_of(s, current.story_id, custom_stamp_id)
    return scope_of(s, story_id if story_id is not None else fallback_story_id, custom_stamp_id)


@contextmanager
def args_scope(args: Mapping[str, Any], fallback_story_id: int | None = None,
               history_model: type[Base] | None = None) -> Iterator[Scope]:
    with get_env_session() as s:
        scope = args_scope_in(s, args, fallback_story_id, history_model)
    with story_scope.scoped(scope):
        yield scope


@contextmanager
def row_scope(model: type[Base], row_id: int, fallback_story_id: int | None = None) -> Iterator[Scope]:
    with get_env_session() as s:
        story_id = story_of_row(s, model, row_id)
        scope = scope_of(s, story_id if story_id is not None else fallback_story_id,
                         custom_stamp_of_row(s, model, row_id))
    with story_scope.scoped(scope):
        yield scope
