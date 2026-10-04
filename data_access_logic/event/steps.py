#!/usr/bin/env python3
"""出来事の db の段(`data_access_logic/step.py`)。流れ(`data_access_logic/flows/`)が、手元では自分のセッションで、web のセッションでは API 越しに呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from data_access_logic.character.moves import move_destinations
from data_access_logic.entrypoint import CommitEntrypoint, record_of, reloaded
from data_access_logic.event import progress, writer
from data_access_logic.event import summary as event_summary
from data_access_logic.event.form import EventCreateForm, EventForm, EventUpdateForm
from data_access_logic.event.plan import EventPlan, finish_generated, plan_event, textless_event
from data_access_logic.event.models import EventSummarySource
from data_access_logic.event.progress_models import EventRecordDraft, LocationSituationMaterial
from data_access_logic.event.record import EventRecord
from data_access_logic.event.writer_models import EventTextDraft, EventTextMaterial
from data_access_logic.location.models import LocationMaterial
from data_access_logic.step import RowId, db_step
from data_access_logic.summary_targets import SummaryTargets
from data_access_logic.query import common_query
from db.schema import Character, Event, EventCharacter, Location
from db.stamp import Stamp


class SummaryScope(BaseModel):
    # 省けばすべての出来事
    event_ids: list[int] | None = None


class SummaryForm(BaseModel):
    event_id: int
    source_hash: str
    text: str


class EventTextForm(BaseModel):
    event_id: int
    # 書けなければ None(本文は空のまま残す)
    draft: EventTextDraft | None


class SituationForm(BaseModel):
    location_id: int
    character_ids: list[int]
    time: Stamp
    # 名前・記録を場面の指定にまとめたもの
    scene: str | None = None


class DestinationsForm(BaseModel):
    location_id: int
    time: Stamp


class ProgressForm(BaseModel):
    situation: SituationForm
    destinations: list[LocationMaterial]
    draft: EventRecordDraft
    # `hidden` / `parent_event_id` / `end` を写す下書き
    event: EventForm


def _characters(s: Session, character_ids: list[int]) -> list[Character]:
    return [s.get_one(Character, character_id) for character_id in character_ids]


@db_step
def stale_summary_sources(s: Session, form: SummaryScope) -> list[EventSummarySource]:
    return event_summary.stale_sources(s, form.event_ids)


@db_step
def write_summary(s: Session, form: SummaryForm) -> None:
    event_summary.write_summary(s, form.event_id, form.source_hash, form.text)


@db_step
def text_targets(s: Session, form: RowId) -> SummaryTargets:
    return writer.text_targets(s, textless_event(s, form.id).id)


@db_step
def text_material(s: Session, form: RowId) -> EventTextMaterial:
    return writer.text_material(s, form.id)


@db_step
def save_event_text(s: Session, form: EventTextForm) -> None:
    writer.save_event_text(s, form.event_id, form.draft)


@db_step
def plan(s: Session, form: EventForm) -> EventPlan:
    return plan_event(s, form)


@db_step
def situation_targets(s: Session, form: SituationForm) -> SummaryTargets:
    return progress.situation_targets(s, form.location_id, _characters(s, form.character_ids), form.time)


@db_step
def situation(s: Session, form: SituationForm) -> LocationSituationMaterial:
    return progress.situation(s, form.location_id, _characters(s, form.character_ids), form.time, form.scene)


@db_step
def destinations(s: Session, form: DestinationsForm) -> list[LocationMaterial]:
    return move_destinations(s, form.location_id, form.time)


@db_step
def save_progress(s: Session, form: ProgressForm) -> EventRecord:
    situation_form = form.situation
    record = progress.save_progress(
        s, situation_form.location_id, _characters(s, situation_form.character_ids), situation_form.time,
        form.destinations, form.draft)
    return record_of(s, EventRecord, finish_generated(s, record.id, form.event))


@db_step
def commit_event(s: Session, form: EventCreateForm) -> EventRecord:
    CommitEntrypoint.check_exists(s, Event, form.parent_event_id, "parent_event_id")
    CommitEntrypoint.check_exists(s, Location, form.location_id, "location_id")
    for character_id in form.character_ids:
        CommitEntrypoint.check_exists(s, Character, character_id, "character_ids")
    record = Event()
    form.write_to(record)
    record.event_characters = [EventCharacter(character_id=character_id) for character_id in form.character_ids]
    s.add(record)
    s.flush()
    return record_of(s, EventRecord, record)


@db_step
def update_event(s: Session, form: EventUpdateForm) -> EventRecord:
    record = reloaded(s, common_query.get_row(s, Event, form.id), selectinload(Event.event_characters))
    if form.parent_event_id == form.id:
        raise ValueError(f"parent_event_id={form.id} が自分自身を指している")
    CommitEntrypoint.check_exists(s, Event, form.parent_event_id, "parent_event_id")
    CommitEntrypoint.check_exists(s, Location, form.location_id, "location_id")
    for character_id in form.character_ids or []:
        CommitEntrypoint.check_exists(s, Character, character_id, "character_ids")
    form.write_changes_to(record)
    if form.character_ids is not None:
        record.event_characters = [EventCharacter(character_id=character_id) for character_id in form.character_ids]
    CommitEntrypoint.finalize(s, record)
    return record_of(s, EventRecord, record)


@db_step
def event_record(s: Session, form: RowId) -> EventRecord:
    return record_of(s, EventRecord, s.get_one(Event, form.id))
