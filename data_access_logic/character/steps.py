#!/usr/bin/env python3
"""人物の db の段(`data_access_logic/step.py`)。web のセッション(`web_session/character.py`)が API 越しに呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.character import generator
from data_access_logic.character.generate_character import generation_time as decide_time
from data_access_logic.character.generate_characters import check_locations
from data_access_logic.character.generator_models import BirthSources, CharacterCreation, CompletionTarget
from data_access_logic.character.record import CharacterHistoryRow, CharacterRecord
from data_access_logic.idea.models import IdeaMaterial
from data_access_logic.step import RowId, RowIds, db_step
from db.stamp import Stamp


class GenerationTimeForm(BaseModel):
    location_id: int | None
    # 省けば世界の最新の出来事の時刻
    time: str | None


class BirthSourcesForm(BaseModel):
    born_location_id: int | None
    time: Stamp
    person: bool


class CompletedHistoriesForm(BaseModel):
    id: int
    histories: list[CharacterHistoryRow]
    # 説明が踏まえたアイデア
    ideas: list[IdeaMaterial]


@db_step
def generation_time(s: Session, form: GenerationTimeForm) -> Stamp:
    return decide_time(s, form.location_id, form.time)


@db_step
def check_generation_locations(s: Session, form: RowIds) -> None:
    check_locations(s, form.ids)


@db_step
def birth_sources(s: Session, form: BirthSourcesForm) -> BirthSources:
    return generator.birth_sources(s, form.born_location_id, form.time, form.person)


@db_step
def save_character(s: Session, form: CharacterCreation) -> CharacterRecord:
    return CharacterRecord.model_validate(generator.save_character(s, form))


@db_step
def completion_target(s: Session, form: RowId) -> CompletionTarget:
    return generator.completion_target(s, form.id)


@db_step
def save_completed_histories(s: Session, form: CompletedHistoriesForm) -> CharacterRecord:
    return CharacterRecord.model_validate(generator.save_completed_histories(s, form.id, form.histories, form.ideas))
