#!/usr/bin/env python3
from __future__ import annotations

import random

from ai.time_keeper._ai import AIClient
from ai.time_keeper._format import format_time
from ai.time_keeper.event_progression_generator import current_place_id
from data_access_logic.event.form import EventForm
from data_access_logic.event.novelist import novelize_event
from data_access_logic.event.progress import progress_place
from data_access_logic.event_seed.extractor import draw as draw_seeds
from data_access_logic.query import common_query, world_createion_query
from data_access_logic.query.base import character_active_condition
from db.schema import Character, Event, Location, Session, Stamp


def _members(session: Session, place_id: int, time: Stamp) -> list[Character]:
    """場所を名指しで頼まれるので、ランダム生成の対象か(active_random_generation)は見ない。"""
    busy_ids = set(session.scalars(world_createion_query.busy_character_ids_select(time)).all())
    characters = session.scalars(
        world_createion_query.alive_characters_select(time)
        .where(character_active_condition()).order_by(Character.id)).all()
    return [character for character in characters
            if character.id not in busy_ids and current_place_id(session, character, time) == place_id]


def generate_at(
    session: Session, ai: AIClient, place_id: int, time: Stamp, key: str,
    rng: random.Random | None = None, shared_style_extra: str = "", style_extra: str = "",
) -> Event | None:
    """居合わせるサブキャラクターを当事者の候補に、その場所・時刻に `key`(ジャンル・場面)に沿った出来事を起こす。"""
    key = (key or "").strip()
    if not key:
        raise ValueError("key(ジャンル・場面の指定)が空")
    place = session.get(Location, place_id)
    if place is None:
        raise ValueError(f"場所 id={place_id} が見つからない")
    if rng is None:
        rng = random.Random(random.randrange(10 ** 9))

    members = _members(session, place_id, time)
    if not members:
        print(f"[time_keepr/place] {place.name}(id={place_id}): "
              f"{format_time(time)} に居合わせて手の空いたサブキャラクターがいない")
        return None
    print(f"[time_keepr/place] {place.name}(id={place_id}) {format_time(time)} の出来事「{key}」: "
          f"居合わせる {', '.join(c.name or '?' for c in members)}")
    seeds = draw_seeds(session, rng)
    print(f"[time_keepr/place] 引いた種: {seeds}")
    record = progress_place(session, ai, rng, place_id, members, time, seeds, scene=key)
    if record is None:
        return None
    return novelize_event(session, ai, record.id, scene=key,
                          shared_style_extra=shared_style_extra, style_extra=style_extra)


def complete_text(
    session: Session, ai: AIClient, record: Event, shared_style_extra: str = "", style_extra: str = "",
) -> Event:
    """出来事の本文(text)が空のとき、記録・当事者・関連する設定から AI に小説の本文だけを書かせて埋める
    (名前・時刻・場所・当事者は変えない)。"""
    if (record.text or "").strip():
        raise ValueError("text はすでに埋まっている")
    return novelize_event(session, ai, record.id, scene=record.name or None,
                          shared_style_extra=shared_style_extra, style_extra=style_extra)


def _members_of_form(session: Session, form: EventForm, place_id: int | None, time: Stamp) -> list[Character]:
    """当事者を名指しされたらその人物(メインキャラクター・手のふさがった者も含む)、
    されなければその場所・時刻に居合わせて手の空いたサブキャラクター。"""
    if not form.character_ids:
        if place_id is None:
            raise ValueError("location_id(場所)か character_ids(当事者)のどちらかは必須")
        return _members(session, place_id, time)
    return [session.get_one(Character, character_id) for character_id in dict.fromkeys(form.character_ids)]


def generate_from_draft(
    session: Session, ai: AIClient, form: EventForm, rng: random.Random | None = None,
    shared_style_extra: str = "", style_extra: str = "",
) -> Event:
    """作者の下書き(GUI の欄の値)から出来事を一件起こす。名前・記録は場面の指定として渡し、
    時刻・場所・当事者は決まった値として使う。空の欄は補う(時刻は世界の最新、場所は当事者の現在地)。
    `hidden` / `parent_event_id` / `end` は下書きの値をそのまま持たせる。"""
    if rng is None:
        rng = random.Random(random.randrange(10 ** 9))
    time = form.time or form.start or session.scalar(common_query.latest_time_select())
    if time is None:
        raise ValueError("time(時刻)が空で、世界にまだ出来事が無いので時刻を決められない")
    members = _members_of_form(session, form, form.location_id, time)
    place_id = form.location_id
    if place_id is None:
        place_id = current_place_id(session, members[0], time)
        if place_id is None:
            raise ValueError(f"人物 id={members[0].id} の {format_time(time)} の居場所が分からないので location_id(場所)を渡す")
    place = session.get(Location, place_id)
    if place is None:
        raise ValueError(f"場所 id={place_id} が見つからない")
    if not members:
        raise ValueError(f"{place.name}(id={place_id})に {format_time(time)} に居合わせて手の空いたサブキャラクターがいない")
    if form.parent_event_id is not None:
        session.get_one(Event, form.parent_event_id)

    scene = form.scene
    print(f"[time_keepr/place] {place.name}(id={place_id}) {format_time(time)} の出来事(下書き「{scene or '(指定なし)'}」): "
          f"当事者の候補 {', '.join(c.name or '?' for c in members)}")
    seeds = draw_seeds(session, rng)
    record = progress_place(session, ai, rng, place_id, members, time, seeds, scene=scene)
    if record is None:
        raise ValueError("出来事の候補が得られなかった")
    record.hidden = form.hidden
    record.parent_event_id = form.parent_event_id
    if form.end is not None:
        record.end = form.end
    session.commit()
    return novelize_event(session, ai, record.id, scene=scene,
                          shared_style_extra=shared_style_extra, style_extra=style_extra)
