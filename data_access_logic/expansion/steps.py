#!/usr/bin/env python3
"""世界の展開の db の段(`data_access_logic/step.py`)。流れ(`data_access_logic/flows/act.py`)が、手元では自分のセッションで、
web のセッションでは API 越しに呼ぶ。書き手(`db/writer.py`)は流れが立て、web ではヘッダで運ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.expansion import acting, routines
from data_access_logic.character.record import CharacterMotivationRecord, CharacterRoutineRow
from data_access_logic.expansion.act_models import (
    ActionsForm, CharacterDayForm, DayBrief, DayBriefForm, DayForm, DayMaterial, DayMaterialForm, DayPlan, DaySaved,
    DaySaveForm, KnownPeople, KnownPeopleForm, MotivesForm, NeedMotivationForm, NewCharacterLink, PeopleForm, PlacePeople,
)
from data_access_logic.expansion.finish_expansion import finish
from data_access_logic.expansion.form import ExpansionCreateForm, ExpansionFinishForm
from data_access_logic.expansion.record import ExpansionRecord
from data_access_logic.expansion.start_expansion import start
from data_access_logic.query import common_query
from data_access_logic.step import db_step
from data_access_logic.summary_targets import SummaryTargets
from db.schema import Expansion


class PromptForm(BaseModel):
    expansion_id: int
    prompt: str


@db_step
def plan_day(s: Session, form: DayForm) -> DayPlan:
    return acting.plan_day(s, form)


@db_step
def routine_targets(s: Session, form: routines.RoutineForm) -> routines.RoutineTargets:
    return routines.routine_targets(s, form)


@db_step
def add_routines(s: Session, form: routines.RoutineAddForm) -> list[CharacterRoutineRow]:
    return routines.add_routines(s, form)


@db_step
def known_people(s: Session, form: KnownPeopleForm) -> KnownPeople:
    return acting.known_people(s, form)


@db_step
def day_brief(s: Session, form: DayBriefForm) -> DayBrief:
    return acting.day_brief(s, form)


@db_step
def people_at(s: Session, form: PeopleForm) -> list[PlacePeople]:
    return acting.people_at(s, form)


@db_step
def save_actions(s: Session, form: ActionsForm) -> None:
    acting.save_actions(s, form)


@db_step
def save_character_day(s: Session, form: CharacterDayForm) -> None:
    acting.save_character_day(s, form)


@db_step
def need_motivations(s: Session, form: NeedMotivationForm) -> list[CharacterMotivationRecord]:
    return acting.need_motivations(s, form)


@db_step
def motive_targets(s: Session, form: MotivesForm) -> SummaryTargets:
    return acting.motive_targets(s, form.character_ids, form.time)


@db_step
def day_material(s: Session, form: DayMaterialForm) -> DayMaterial:
    return acting.day_material(s, form)


@db_step
def start_expansion(s: Session, form: ExpansionCreateForm) -> ExpansionRecord:
    return start(s, form)


@db_step
def note_prompt(s: Session, form: PromptForm) -> None:
    common_query.get_row(s, Expansion, form.expansion_id).prompt = form.prompt


@db_step
def finish_expansion(s: Session, form: ExpansionFinishForm) -> ExpansionRecord:
    return finish(s, form)


@db_step
def save_day(s: Session, form: DaySaveForm) -> DaySaved:
    return acting.save_day(s, form)


@db_step
def link_new_character(s: Session, form: NewCharacterLink) -> None:
    acting.link_new_character(s, form)
