#!/usr/bin/env python3
from __future__ import annotations

import random

from ai.claude_code import ai_client
from data_access_logic.entrypoint import SessionEntrypoint, record_of
from data_access_logic.event.form import EventForm
from data_access_logic.event.novelist import novelize_event
from data_access_logic.event.progress import progress_place
from data_access_logic.event.record import EventRecord
from data_access_logic.event_seed.extractor import draw as draw_seeds, refresh_and_consolidate
from data_access_logic.query import common_query, world_createion_query
from data_access_logic.query.base import character_active_condition
from db.schema import Character, Event, Location, Session, Stamp, get_env_session


def _current_place_id(session: Session, character: Character, time: Stamp) -> int | None:
    place = session.scalars(common_query.character_place_select(character.id, time)).first()
    return place.location_id if place else None


def _present_characters(session: Session, place_id: int, time: Stamp) -> list[Character]:
    """その場所・時刻に居合わせて手の空いたサブキャラクター。場所を名指しされるので、
    ランダム生成の対象か(active_random_generation)は見ない。"""
    busy_ids = set(session.scalars(world_createion_query.busy_character_ids_select(time)).all())
    characters = session.scalars(
        world_createion_query.alive_characters_select(time)
        .where(character_active_condition()).order_by(Character.id)).all()
    return [character for character in characters
            if character.id not in busy_ids and _current_place_id(session, character, time) == place_id]


class GenerateEvent(SessionEntrypoint):
    """作者の下書き(GUI の欄の値。全部空でもよい)を核に、出来事を一件 AI に組み立てさせて足す。

    候補を挙げてサイコロで選び、記録して小説の本文にする生成を、
    下書きの名前・記録を場面の指定に、時刻・場所・当事者を決まった値として回す。
    時刻を省けば世界の最新の出来事の時刻、場所を省けば当事者の現在地、当事者を省けばその場所・時刻に居合わせるサブキャラクター。
    `shared_style_extra` / `style_extra` は世界ごとの文体の好み(世界リポジトリの `instructions/style.py`)。

    `id` を渡せば、その出来事の本文(text)が空のときに限り、記録・当事者・関連する設定から AI に
    小説の本文だけを書かせて埋める(名前・時刻・場所・当事者は変えない)。
    """

    def __init__(self, event: EventForm | None = None, seed: int | None = None,
                 shared_style_extra: str = "", style_extra: str = "", ai=ai_client):
        self.event = event or EventForm()
        self.seed = seed
        self.shared_style_extra = shared_style_extra
        self.style_extra = style_extra
        self.ai = ai

    def execute(self, session) -> EventRecord:
        if self.event.id is not None:
            record = common_query.get_row(session, Event, self.event.id)
            if (record.text or "").strip():
                raise ValueError("text はすでに埋まっている")
            written = novelize_event(session, self.ai, record.id, scene=record.name or None,
                                     shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
        else:
            written = self._generate(session, random.Random(self.seed))
        return record_of(session, EventRecord, written)

    def result(self) -> EventRecord:
        """足した出来事の本文も種の元になるので、確定したあとに別のセッションで種を抜き出す
        (AI が答えなくても出来事は残す)。"""
        with get_env_session() as session:
            generated = self.execute(session)
        with get_env_session() as session:
            refresh_and_consolidate(session, self.ai)
        return generated

    def _members(self, session: Session, place_id: int | None, time: Stamp) -> list[Character]:
        """当事者を名指しされたらその人物(メインキャラクター・手のふさがった者も含む)、
        されなければその場所・時刻に居合わせて手の空いたサブキャラクター。"""
        if not self.event.character_ids:
            if place_id is None:
                raise ValueError("location_id(場所)か character_ids(当事者)のどちらかは必須")
            return _present_characters(session, place_id, time)
        return [session.get_one(Character, character_id) for character_id in dict.fromkeys(self.event.character_ids)]

    def _generate(self, session: Session, rng: random.Random) -> Event:
        """名前・記録は場面の指定として渡し、時刻・場所・当事者は決まった値として使う。
        `hidden` / `parent_event_id` / `end` は下書きの値をそのまま持たせる。"""
        form = self.event
        time = form.time or form.start or session.scalar(common_query.latest_time_select())
        if time is None:
            raise ValueError("time(時刻)が空で、世界にまだ出来事が無いので時刻を決められない")
        members = self._members(session, form.location_id, time)
        place_id = form.location_id
        if place_id is None:
            place_id = _current_place_id(session, members[0], time)
            if place_id is None:
                raise ValueError(f"人物 id={members[0].id} の {time} の居場所が分からないので location_id(場所)を渡す")
        place = common_query.get_row(session, Location, place_id)
        if not members:
            raise ValueError(f"{place.name}(id={place_id})に {time} に居合わせて手の空いたサブキャラクターがいない")
        if form.parent_event_id is not None:
            session.get_one(Event, form.parent_event_id)

        scene = form.scene
        print(f"[data_access_logic/event] {place.name}(id={place_id}) {time} の出来事(下書き「{scene or '(指定なし)'}」): "
              f"当事者の候補 {', '.join(c.name or '?' for c in members)}")
        seeds = draw_seeds(session, rng)
        record = progress_place(session, self.ai, rng, place_id, members, time, seeds, scene=scene)
        if record is None:
            raise ValueError("出来事の候補が得られなかった")
        record.hidden = form.hidden
        record.parent_event_id = form.parent_event_id
        if form.end is not None:
            record.end = form.end
        session.commit()
        return novelize_event(session, self.ai, record.id, scene=scene,
                              shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
