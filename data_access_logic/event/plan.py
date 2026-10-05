#!/usr/bin/env python3
"""出来事を起こす前に、時刻・場所・当事者を決める(段 `event.steps.plan` / `text_targets` が使う)。"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from data_access_logic.event.form import EventForm
from data_access_logic.material import Material
from data_access_logic.query import common_query, world_creation_query
from db.schema import Character, CharacterLocation, Event, Location
from db.stamp import Stamp

logger = logging.getLogger(__name__)


def _current_location_id(character: Character, time: Stamp) -> int | None:
    """`common_query.character_location_select` と同じ選び方(その時刻に続く行のうち、始まりの新しいもの)を、
    読み込み済みの `locations` で行う(人物ごとに問い合わせ直さない)。"""
    current = [row for row in character.locations
               if (row.start is None or row.start <= time) and (row.end is None or row.end > time)]
    if not current:
        return None
    dated = [row for row in current if row.start is not None]
    return max(dated, key=lambda row: (row.start, row.id)).location_id if dated else max(
        current, key=lambda row: row.id).location_id


def _present_characters(s: Session, location_id: int, time: Stamp) -> list[Character]:
    """その場所・時刻に居合わせて手の空いたサブキャラクター。場所を名指しされるので、
    ランダム生成の対象か(active_random_generation)は見ない。"""
    busy_ids = set(s.scalars(world_creation_query.busy_character_ids_select(time)).all())
    characters = s.scalars(
        world_creation_query.alive_characters_select(time)
        .where(world_creation_query.character_active_condition(),
               Character.locations.any(CharacterLocation.location_id == location_id))
        .order_by(Character.id)).all()
    return [character for character in characters
            if character.id not in busy_ids and _current_location_id(character, time) == location_id]


class EventPlan(Material):
    """起こす出来事の、決まった時刻・場所・当事者。"""

    time: Stamp
    location_id: int
    character_ids: list[int]


def _members(s: Session, form: EventForm, location_id: int | None, time: Stamp) -> list[Character]:
    """当事者を名指しされたらその人物(メインキャラクター・手のふさがった者も含む)、
    されなければその場所・時刻に居合わせて手の空いたサブキャラクター。"""
    if not form.character_ids:
        if location_id is None:
            raise ValueError("location_id(場所)か character_ids(当事者)のどちらかは必須")
        return _present_characters(s, location_id, time)
    return [s.get_one(Character, character_id) for character_id in dict.fromkeys(form.character_ids)]


def plan_event(s: Session, form: EventForm) -> EventPlan:
    """時刻を省けば世界の最新の出来事の時刻、場所を省けば当事者の現在地、当事者を省けばその場所・時刻に居合わせるサブキャラクター。"""
    time = form.time or form.start or s.scalar(common_query.latest_time_select())
    if time is None:
        raise ValueError("time(時刻)が空で、世界にまだ出来事が無いので時刻を決められない")
    members = _members(s, form, form.location_id, time)
    location_id = form.location_id
    if location_id is None:
        location_id = _current_location_id(members[0], time)
        if location_id is None:
            raise ValueError(f"人物 id={members[0].id} の {time} の居場所が分からないので location_id(場所)を渡す")
    location = common_query.get_row(s, Location, location_id)
    if not members:
        raise ValueError(f"{location.name}(id={location_id})に {time} に居合わせて手の空いたサブキャラクターがいない")
    if form.parent_event_id is not None:
        s.get_one(Event, form.parent_event_id)
    logger.info(f"{location.name}(id={location_id}) {time} の出来事(下書き「{form.scene or '(指定なし)'}」): "
                f"当事者の候補 {', '.join(c.name or '?' for c in members)}")
    return EventPlan(time=time, location_id=location_id, character_ids=[member.id for member in members])


def finish_generated(s: Session, event_id: int, form: EventForm) -> Event:
    """`hidden` / `parent_event_id` / `end` は下書きの値をそのまま持たせる。"""
    record = s.get_one(Event, event_id)
    record.hidden = form.hidden
    record.parent_event_id = form.parent_event_id
    if form.end is not None:
        record.end = form.end
    s.flush()
    return record


def textless_event(s: Session, event_id: int) -> Event:
    record = common_query.get_row(s, Event, event_id)
    if (record.text or "").strip():
        raise ValueError("text はすでに埋まっている")
    return record
