#!/usr/bin/env python3
from __future__ import annotations

import random

from sqlalchemy.orm import Session

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.character.form import CharacterForm
from data_access_logic.character.generator import complete_text, generate_character
from data_access_logic.character.record import CharacterRecord
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.query import common_query
from db.schema import CHARACTER_KIND_PERSON, Location, Stamp


def generation_time(s: Session, location_id: int | None, time: Stamp | str | None) -> Stamp:
    """`time` を省けば世界の最新の出来事の時刻。`location_id` があれば、その場所があるかも確かめる。"""
    if location_id is not None:
        common_query.get_row(s, Location, location_id)
    decided = Stamp.parse(time) or s.scalar(common_query.latest_time_select())
    if decided is None:
        raise ValueError("time(現在の時刻)が空で、世界にまだ出来事が無いので時刻を決められない")
    return decided


class GenerateCharacter(SessionEntrypoint):
    """作者の下書き(GUI の欄の値。全部空でもよい)を核に、人物を一人 AI に組み立てさせて足す。

    時の流れの中で生む人物と同じ自動生成(`generate_character`。性格・ミーム・来歴・名づけまで AI が決める)を、
    下書きの名前・説明を核に、性別・体格・口調・性格・種別・生年・没年・メインキャラクターかを決まった値として回す。
    `time`(現在の時刻)を省けば世界の最新の出来事の時刻。

    `id` を渡せば、その人物の本文(text)が空のときに限り、決まっている名前・属性・出自を核に AI に
    本文だけを書かせて埋める(性別・体格・口調・性格・種別・生年・没年・名前は変えない)。
    """

    def __init__(self, character: CharacterForm | None = None, time: Stamp | str | None = None,
                 seed: int | None = None, ai: AIClient = ai_client):
        self.character = character or CharacterForm()
        self.time = time
        self.seed = seed
        self.ai = ai

    def execute(self, s: Session) -> CharacterRecord:
        form = self.character
        rng = random.Random(self.seed)
        if form.id is not None:
            return CharacterRecord.model_validate(complete_text(s, self.ai, rng, form.id))
        time = generation_time(s, form.location_id, self.time)
        person = (form.kind or CHARACTER_KIND_PERSON) == CHARACTER_KIND_PERSON
        record = generate_character(s, self.ai, rng, form.location_id, time, person, form)
        if record is None:
            raise ValueError("人物の中身が得られなかった")
        return CharacterRecord.model_validate(record)
