#!/usr/bin/env python3
from __future__ import annotations

import logging
import random

from ai.claude_code import ai_client
from data_access_logic import world_style
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import SessionEntrypoint, record_of
from data_access_logic.event.form import EventForm
from data_access_logic.event.novelist import novelize_event
from data_access_logic.event.progress import progress_location
from data_access_logic.event.record import EventRecord
from data_access_logic.event_seed.extractor import draw as draw_seeds
from data_access_logic.event_seed.extractor import refresh_and_consolidate
from data_access_logic.query import common_query, world_creation_query
from db.schema import Character, Event, Location, Session, Stamp, get_env_session

logger = logging.getLogger(__name__)


def _current_location_id(s: Session, character: Character, time: Stamp) -> int | None:
    character_location = s.scalars(common_query.character_location_select(character.id, time)).first()
    return character_location.location_id if character_location else None


def _present_characters(s: Session, location_id: int, time: Stamp) -> list[Character]:
    """その場所・時刻に居合わせて手の空いたサブキャラクター。場所を名指しされるので、
    ランダム生成の対象か(active_random_generation)は見ない。"""
    busy_ids = set(s.scalars(world_creation_query.busy_character_ids_select(time)).all())
    characters = s.scalars(
        world_creation_query.alive_characters_select(time)
        .where(world_creation_query.character_active_condition()).order_by(Character.id)).all()
    return [character for character in characters
            if character.id not in busy_ids and _current_location_id(s, character, time) == location_id]


class GenerateEvent(SessionEntrypoint):
    """作者の下書き(GUI の欄の値。全部空でもよい)を核に、出来事を一件 AI に組み立てさせて足す。

    候補を挙げてサイコロで選び、記録して小説の本文にする生成を、
    下書きの名前・記録を場面の指定に、時刻・場所・当事者を決まった値として回す。
    時刻を省けば世界の最新の出来事の時刻、場所を省けば当事者の現在地、当事者を省けばその場所・時刻に居合わせるサブキャラクター。
    `shared_style_extra` / `style_extra` は世界ごとの文体の好み。省けば世界リポジトリの `instructions/style.py` から読む。

    `id` を渡せば、その出来事の本文(text)が空のときに限り、記録・当事者・関連する設定から AI に
    小説の本文だけを書かせて埋める(名前・時刻・場所・当事者は変えない)。
    """

    def __init__(self, event: EventForm | None = None, seed: int | None = None,
                 shared_style_extra: str | None = None, style_extra: str | None = None, ai: AIClient = ai_client):
        self.event = event or EventForm()
        self.seed = seed
        self.shared_style_extra = world_style.shared_style_extra(shared_style_extra)
        self.style_extra = world_style.style_extra(style_extra)
        self.ai = ai

    def execute(self, s: Session) -> EventRecord:
        if self.event.id is not None:
            record = common_query.get_row(s, Event, self.event.id)
            if (record.text or "").strip():
                raise ValueError("text はすでに埋まっている")
            written = novelize_event(s, self.ai, record.id, scene=record.name or None,
                                     shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
        else:
            written = self._generate(s, random.Random(self.seed))
        return record_of(s, EventRecord, written)

    def result(self) -> EventRecord:
        """足した出来事の本文も種の元になるので、確定したあとに別のセッションで種を抜き出す
        (AI が答えなくても出来事は残す)。"""
        with get_env_session() as s:
            generated = self.execute(s)
        with get_env_session() as s:
            refresh_and_consolidate(s, self.ai)
        return generated

    def _members(self, s: Session, location_id: int | None, time: Stamp) -> list[Character]:
        """当事者を名指しされたらその人物(メインキャラクター・手のふさがった者も含む)、
        されなければその場所・時刻に居合わせて手の空いたサブキャラクター。"""
        if not self.event.character_ids:
            if location_id is None:
                raise ValueError("location_id(場所)か character_ids(当事者)のどちらかは必須")
            return _present_characters(s, location_id, time)
        return [s.get_one(Character, character_id) for character_id in dict.fromkeys(self.event.character_ids)]

    def _generate(self, s: Session, rng: random.Random) -> Event:
        """名前・記録は場面の指定として渡し、時刻・場所・当事者は決まった値として使う。
        `hidden` / `parent_event_id` / `end` は下書きの値をそのまま持たせる。"""
        form = self.event
        time = form.time or form.start or s.scalar(common_query.latest_time_select())
        if time is None:
            raise ValueError("time(時刻)が空で、世界にまだ出来事が無いので時刻を決められない")
        members = self._members(s, form.location_id, time)
        location_id = form.location_id
        if location_id is None:
            location_id = _current_location_id(s, members[0], time)
            if location_id is None:
                raise ValueError(f"人物 id={members[0].id} の {time} の居場所が分からないので location_id(場所)を渡す")
        location = common_query.get_row(s, Location, location_id)
        if not members:
            raise ValueError(f"{location.name}(id={location_id})に {time} に居合わせて手の空いたサブキャラクターがいない")
        if form.parent_event_id is not None:
            s.get_one(Event, form.parent_event_id)

        scene = form.scene
        logger.info(f"{location.name}(id={location_id}) {time} の出来事(下書き「{scene or '(指定なし)'}」): "
              f"当事者の候補 {', '.join(c.name or '?' for c in members)}")
        seeds = draw_seeds(s, rng)
        record = progress_location(s, self.ai, rng, location_id, members, time, seeds, scene=scene)
        if record is None:
            raise ValueError("出来事の候補が得られなかった")
        record.hidden = form.hidden
        record.parent_event_id = form.parent_event_id
        if form.end is not None:
            record.end = form.end
        s.commit()
        return novelize_event(s, self.ai, record.id, scene=scene,
                              shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
