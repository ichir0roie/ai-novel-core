#!/usr/bin/env python3
"""話の db の段(`data_access_logic/step.py`)。流れ(`data_access_logic/flows/`)が、手元では自分のセッションで、web のセッションでは API 越しに呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode import brief, episode_memory, outcomes
from data_access_logic.episode import summary as episode_summary
from data_access_logic.episode.outcomes import AppliedOutcomes, OutcomesForm, ReflectMaterial
from data_access_logic.episode.form import EpisodeCommitForm, EpisodeReviseForm, set_characters
from data_access_logic.episode.mentions import save_mentions
from data_access_logic.episode.models import EpisodeBrief
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.idea.models import IdeaDraft
from data_access_logic.step import RowId, db_step
from data_access_logic.summary_targets import SummaryTargets
from data_access_logic.query import common_query
from db.schema import Character, Episode, Location, Story


class BriefForm(BaseModel):
    episode_id: int
    # プロット・話のセッションの行・今の本文から AI が挙げた、アイデアと照らす語
    keywords: list[IdeaDraft]


@db_step
def brief_targets(s: Session, form: RowId) -> brief.BriefTargets:
    return brief.brief_targets(s, form.id)


@db_step
def episode_brief(s: Session, form: BriefForm) -> EpisodeBrief:
    return brief.episode_brief(s, form.episode_id, form.keywords)


@db_step
def commit_episode(s: Session, form: EpisodeCommitForm) -> EpisodeRecord:
    CommitEntrypoint.check_exists(s, Story, form.story_id, "story_id")
    CommitEntrypoint.check_exists(s, Character, form.viewpoint_character_id, "viewpoint_character_id")
    CommitEntrypoint.check_exists(s, Location, form.location_id, "location_id")
    for character_id in form.character_ids or []:
        CommitEntrypoint.check_exists(s, Character, character_id, "character_ids")

    if form.id is None:
        record = Episode(plot_text="", title="")
        s.add(record)
    else:
        record = common_query.get_row(s, Episode, form.id)
    form.write_changes_to(record)
    CommitEntrypoint.finalize(s, record)
    # 渡されなければ既存の登場人物はそのまま
    if form.character_ids is not None:
        set_characters(s, record.id, form.character_ids)
    save_mentions(s, record.id)
    return record_of(s, EpisodeRecord, record)


@db_step
def revise_episode(s: Session, form: EpisodeReviseForm) -> EpisodeRecord:
    commit = EpisodeCommitForm(id=form.id, main_text=form.main_text)
    # 渡した欄だけが書かれるので、プロット・題は渡されたときだけ欄に入れる(None を入れると空で上書きする)
    if form.plot_text is not None:
        commit.plot_text = form.plot_text
    if form.title is not None:
        commit.title = form.title
    return commit_episode(s, commit)


@db_step
def episode_record(s: Session, form: RowId) -> EpisodeRecord:
    return record_of(s, EpisodeRecord, s.get_one(Episode, form.id))


@db_step
def reflect_material(s: Session, form: RowId) -> ReflectMaterial | None:
    return outcomes.reflect_material(s, form.id)


@db_step
def apply_outcomes(s: Session, form: OutcomesForm) -> AppliedOutcomes:
    return outcomes.apply_outcomes(s, form)



class EpisodeSummaryScope(BaseModel):
    # 省けばすべての話
    episode_ids: list[int] | None = None


class EpisodeSummaryForm(BaseModel):
    episode_id: int
    source_hash: str
    text: str


@db_step
def stale_summary_sources(s: Session, form: EpisodeSummaryScope) -> list[episode_summary.EpisodeSummarySource]:
    return episode_summary.stale_sources(s, form.episode_ids)


@db_step
def write_summary(s: Session, form: EpisodeSummaryForm) -> None:
    episode_summary.write_summary(s, form.episode_id, form.source_hash, form.text)


@db_step
def cast_episode_targets(s: Session, form: RowId) -> SummaryTargets:
    """話の登場人物の人物役が「居合わせた話」として読む、前の話(要約を揃えておく話)。"""
    return SummaryTargets(episode_ids=episode_memory.cast_past_episode_ids(s, form.id))
