#!/usr/bin/env python3
"""世界の展開の db の段(`data_access_logic/step.py`)。流れ(`data_access_logic/flows/act.py`)が、手元では自分のセッションで、
web のセッションでは API 越しに呼ぶ。書き手(`db/writer.py`)は流れが立て、web ではヘッダで運ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.expansion import acting
from data_access_logic.expansion.act_models import ActorBrief, ActorPick, ActSaved, ActSaveForm, NewCharacterLink
from data_access_logic.expansion.finish_expansion import finish
from data_access_logic.expansion.form import ExpansionCreateForm, ExpansionFinishForm
from data_access_logic.expansion.record import ExpansionRecord
from data_access_logic.expansion.start_expansion import start
from data_access_logic.query import common_query
from data_access_logic.step import db_step
from db.schema import Expansion
from db.stamp import Stamp


class PickForm(BaseModel):
    character_id: int | None = None
    time: Stamp | None = None
    seed: int | None = None


class BriefForm(BaseModel):
    pick: ActorPick
    seeds: list[str]
    nudge: str | None = None


class PromptForm(BaseModel):
    expansion_id: int
    prompt: str


@db_step
def pick_actor(s: Session, form: PickForm) -> ActorPick:
    return acting.pick_actor(s, form.character_id, form.time, form.seed)


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
def actor_brief(s: Session, form: BriefForm) -> ActorBrief:
    return acting.actor_brief(s, form.pick, form.seeds, form.nudge)


@db_step
def save_act(s: Session, form: ActSaveForm) -> ActSaved:
    return acting.save_act(s, form)


@db_step
def link_new_character(s: Session, form: NewCharacterLink) -> None:
    acting.link_new_character(s, form)
