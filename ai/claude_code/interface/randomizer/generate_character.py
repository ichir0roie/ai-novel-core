#!/usr/bin/env python3
from __future__ import annotations

import random

from ai.claude_code import ai_client
from ai.claude_code.interface._base import SessionEntrypoint, UnknownRecordError
from ai.time_keeper.random_character_generator import _generate_one, complete_text
from data_access_logic.query import common_query
from db.schema import CHARACTER_KIND_PERSON, Character, Location, Stamp
from db.schema_pydantic import to_dict


class GenerateCharacter(SessionEntrypoint):
    """作者の下書き(GUI の欄の値。全部空でもよい)を核に、人物を一人 AI に組み立てさせて足す。

    時の流れの中で生む人物と同じ自動生成(`_generate_one`。性格・ミーム・来歴・名づけまで AI が決める)を、
    下書きの名前・説明を核に、性別・体格・口調・性格・種別・生年・没年・メインキャラクターかを決まった値として回す。
    `time`(現在の時刻)を省けば世界の最新の出来事の時刻。

    `id` を渡せば、その人物の本文(text)が空のときに限り、決まっている名前・属性・出自を核に AI に
    本文だけを書かせて埋める(性別・体格・口調・性格・種別・生年・没年・名前は変えない)。
    """

    def __init__(self, character: dict | None = None, time: Stamp | str | None = None,
                 seed: int | None = None, ai=ai_client):
        self.character = dict(character or {})
        self.time = time
        self.seed = seed
        self.ai = ai

    def execute(self, session) -> dict:
        draft = dict(self.character)
        character_id = draft.pop("id", None)
        if character_id is not None:
            return self._complete(session, character_id)
        place_id = draft.pop("place_id", None)
        place = None
        if place_id is not None:
            place = session.get(Location, place_id)
            if place is None:
                raise UnknownRecordError(f"place_id={place_id} という id の location が見つからない")
        time = Stamp.parse(self.time) or session.scalar(common_query.latest_time_select())
        if time is None:
            raise ValueError("time(現在の時刻)が空で、世界にまだ出来事が無いので時刻を決められない")
        person = (draft.get("kind") or CHARACTER_KIND_PERSON) == CHARACTER_KIND_PERSON
        record = _generate_one(session, place, time, random.Random(self.seed), self.ai, person=person, hints=draft)
        return {**to_dict(record), "place_id": place_id}

    def _complete(self, session, character_id: int) -> dict:
        record = session.get(Character, character_id)
        if record is None:
            raise UnknownRecordError(f"id={character_id} という人物が見つからない")
        if (record.text or "").strip():
            raise ValueError("text はすでに埋まっている")
        born_place = session.get(Location, record.places[-1].location_id) if record.places else None
        record.text = complete_text(session, record, born_place, self.ai)
        session.commit()
        return to_dict(record)
