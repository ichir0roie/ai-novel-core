#!/usr/bin/env python3
"""人物の db の段(`data_access_logic/step.py`)。流れ(`data_access_logic/flows/`)が、手元では自分のセッションで、web のセッションでは API 越しに呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.character import generator
from data_access_logic.character.generator_models import BirthSources, CharacterCreation, CharacterWriting, CompletionTarget
from data_access_logic.character.moves import update_locations
from data_access_logic.character.record import CharacterMove, CharacterRecord
from data_access_logic.query import common_query, world_creation_query
from data_access_logic.step import RowId, RowIds, db_step
from db.schema import Location
from db.stamp import Stamp


class GenerationTimeForm(BaseModel):
    location_id: int | None
    # 省けば世界の最新の出来事の時刻
    time: str | None


class BirthSourcesForm(BaseModel):
    born_location_id: int | None
    time: Stamp
    person: bool


class ResidentRoomsForm(BaseModel):
    location_ids: list[int]
    time: Stamp


class MovesForm(BaseModel):
    moves: list[CharacterMove]
    # 移した時刻
    time: Stamp


class CompletedTextForm(BaseModel):
    id: int
    writing: CharacterWriting


@db_step
def generation_time(s: Session, form: GenerationTimeForm) -> Stamp:
    """`time` を省けば世界の最新の出来事の時刻。`location_id` があれば、その場所があるかも確かめる。"""
    if form.location_id is not None:
        common_query.get_row(s, Location, form.location_id)
    decided = Stamp.parse(form.time) or s.scalar(common_query.latest_time_select())
    if decided is None:
        raise ValueError("time(現在の時刻)が空で、世界にまだ出来事が無いので時刻を決められない")
    return decided


@db_step
def check_generation_locations(s: Session, form: RowIds) -> None:
    for location_id in form.ids:
        common_query.get_row(s, Location, location_id)
        world_creation_query.check_has_story(s, location_id, "character")


@db_step
def generation_rooms(s: Session, form: ResidentRoomsForm) -> dict[int, int]:
    """場所ごとに、上限(`constants.RESIDENT_LIMITS`)まであと何人足せるか。"""
    rooms = {}
    for location_id in form.location_ids:
        location = common_query.get_row(s, Location, location_id)
        limit = constants.RESIDENT_LIMITS.get(location.kind or "", constants.DEFAULT_RESIDENT_LIMIT)
        residents = s.scalar(select(func.count()).select_from(
            common_query.resident_character_ids_select([location_id], form.time).subquery())) or 0
        rooms[location_id] = max(0, limit - residents)
    return rooms


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
def save_completed_text(s: Session, form: CompletedTextForm) -> CharacterRecord:
    return CharacterRecord.model_validate(generator.save_completed_text(s, form.id, form.writing))


@db_step
def move_characters(s: Session, form: MovesForm) -> list[CharacterMove]:
    return update_locations(s, form.moves, form.time)
