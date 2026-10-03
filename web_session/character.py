#!/usr/bin/env python3
"""人物・対象の生成を、API 越しに回す。

引数は `data_access_logic/character/` の入口(`GenerateCharacter` / `GenerateCharacters`)と同じ。db の段は
`data_access_logic/character/steps.py`、AI・乱数の段は `data_access_logic/character/generator.py` の `character_content` など。
"""
from __future__ import annotations

import random

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.character import generator
from data_access_logic.character import steps as character_steps
from data_access_logic.character.form import CharacterForm
from data_access_logic.character.generate_characters import capped_count
from data_access_logic.character.record import CharacterRecord, GeneratedCharacter
from data_access_logic.idea import steps as idea_steps
from data_access_logic.idea.search import keywords_of
from data_access_logic.step import RowId, RowIds
from db.schema import CHARACTER_KIND_PERSON
from db.stamp import Stamp
from web_session.api import call


def generate(
    ai: AIClient, rng: random.Random, born_location_id: int | None, time: Stamp, person: bool,
    form: CharacterForm | None = None, plot_text: str | None = None,
) -> CharacterRecord | None:
    """一件生んで足す。中身が得られなければ足さずに None。AI が洗い出した語から足した候補のアイデアは、照らす段で確定する。
    `plot_text` は登場させる話のプロット(`generator.character_content`)。"""
    sources = call(character_steps.birth_sources,
                   character_steps.BirthSourcesForm(born_location_id=born_location_id, time=time, person=person))
    decided = generator.character_content(ai, rng, sources, time, person, form, plot_text)
    if decided is None:
        return None
    ideas = call(idea_steps.resolve_ideas, idea_steps.ResolveForm(
        keywords=keywords_of(decided.content.text, ai, time), location_id=born_location_id, time=time))
    return call(character_steps.save_character, generator.character_creation(ai, rng, decided, ideas, born_location_id, form))


def _complete_text(ai: AIClient, rng: random.Random, character_id: int) -> CharacterRecord:
    target = call(character_steps.completion_target, RowId(id=character_id))
    sources = call(character_steps.birth_sources, character_steps.BirthSourcesForm(
        born_location_id=target.born_location_id, time=target.time, person=target.person))
    material, content = generator.completion_content(ai, rng, target, sources)
    ideas = call(idea_steps.resolve_ideas, idea_steps.ResolveForm(
        keywords=keywords_of(content.text, ai, target.time), location_id=target.born_location_id, time=target.time))
    return call(character_steps.save_completed_text, character_steps.CompletedTextForm(
        id=character_id, writing=generator.completed_text(ai, target, material, content, ideas)))


def generate_character(
    character: CharacterForm | None = None, time: Stamp | str | None = None, seed: int | None = None,
    plot_text: str | None = None, ai: AIClient = ai_client,
) -> CharacterRecord:
    """`GenerateCharacter` に当たる。`id` を渡せば、その人物の芯(text)が空のときに限り説明と来歴だけを埋める。"""
    form = character or CharacterForm()
    rng = random.Random(seed)
    if form.id is not None:
        return _complete_text(ai, rng, form.id)
    decided_time = call(character_steps.generation_time, character_steps.GenerationTimeForm(
        location_id=form.location_id, time=None if time is None else str(time)))
    person = (form.kind or CHARACTER_KIND_PERSON) == CHARACTER_KIND_PERSON
    record = generate(ai, rng, form.location_id, decided_time, person, form, plot_text)
    if record is None:
        raise ValueError("人物の中身が得られなかった")
    return record


def generate_characters(
    location_ids: list[int], time: Stamp | str, count: tuple[int, int] = (2, 4), person: bool = True,
    seed: int | None = None, ai: AIClient = ai_client,
) -> list[GeneratedCharacter]:
    """`GenerateCharacters` に当たる。一人ごとに書き戻すので、途中で止まっても作った人物は残る。"""
    call(character_steps.check_generation_locations, RowIds(ids=location_ids))
    at = Stamp.parse(time)
    if at is None:
        raise ValueError("time(現在の時刻)が空")
    rooms = call(character_steps.generation_rooms,
                 character_steps.ResidentRoomsForm(location_ids=location_ids, time=at))
    rng = random.Random(seed)
    created = []
    for location_id in location_ids:
        for _ in range(capped_count(rng, count, location_id, rooms[location_id])):
            record = generate(ai, rng, location_id, at, person)
            if record is not None:
                created.append(GeneratedCharacter(id=record.id, name=record.name, location_id=location_id))
    return created
