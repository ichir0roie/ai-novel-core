#!/usr/bin/env python3
"""話の db の段(`data_access_logic/step.py`)。web のセッション(`web_session/episode.py`)が API 越しに呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import record_of
from data_access_logic.episode import framer, plot_completer, reviser, writer
from data_access_logic.episode import summary as episode_summary
from data_access_logic.episode.commit_episode import CommitEpisode
from data_access_logic.episode.form import EpisodeCommitForm, EpisodeForm, save_frame
from data_access_logic.episode.models import (
    EpisodeDraft, EpisodeFrameDraft, EpisodeFrameMaterial, EpisodeLocationCandidateDraft, EpisodeMaterial,
    EpisodeRevisionDraft, EpisodeRevisionMaterial, EpisodeSummarySource,
)
from data_access_logic.episode.record import EpisodeRecord, EpisodeSummaryRecord
from data_access_logic.idea.models import IdeaMaterial, IdeaTerm
from data_access_logic.location.models import LocationMaterial
from data_access_logic.step import RowId, db_step
from data_access_logic.summary_targets import SummaryTargets
from db.schema import Episode
from db.stamp import Stamp


class SavedFrame(BaseModel):
    id: int
    # プロットか時刻が空なので、本文を書く前に枠を決める
    needs_frame: bool


class SummarySourcesForm(BaseModel):
    # 省けばすべての話
    episode_ids: list[int] | None = None
    # false なら、概要が本文と揃っていても作り直す
    stale_only: bool = True


class SummaryForm(BaseModel):
    episode_id: int
    source_hash: str
    summary_text: str


class MaterialForm(BaseModel):
    episode_id: int
    # 話のプロットから AI が挙げた、アイデアと照らす語
    keywords: list[IdeaTerm]


class WrittenForm(BaseModel):
    episode_id: int
    draft: EpisodeDraft
    # 本文が踏まえたアイデア
    ideas: list[IdeaMaterial]


class FrameForm(BaseModel):
    episode_id: int
    draft: EpisodeFrameDraft
    start: Stamp


class RevisionForm(BaseModel):
    episode_id: int
    draft: EpisodeRevisionDraft
    instruction: str


class PlotForm(BaseModel):
    episode_id: int
    plot_text: str


class LocationScope(BaseModel):
    location_id: int | None


class CastMemberForm(BaseModel):
    episode_id: int
    character_id: int


class NewLocationForm(BaseModel):
    episode_id: int
    candidate: EpisodeLocationCandidateDraft
    parent_id: int | None


@db_step
def save_episode_frame(s: Session, form: EpisodeForm) -> SavedFrame:
    record = save_frame(s, form)
    return SavedFrame(id=record.id, needs_frame=not record.plot_text.strip() or record.start is None)


@db_step
def summary_sources(s: Session, form: SummarySourcesForm) -> list[EpisodeSummarySource]:
    return episode_summary.summary_sources(s, form.episode_ids, form.stale_only)


@db_step
def write_summary(s: Session, form: SummaryForm) -> EpisodeSummaryRecord:
    return EpisodeSummaryRecord.model_validate(
        episode_summary.write_summary(s, form.episode_id, form.source_hash, form.summary_text))


@db_step
def writing_targets(s: Session, form: RowId) -> writer.WritingTargets:
    return writer.writing_targets(s, form.id)


@db_step
def episode_material(s: Session, form: MaterialForm) -> EpisodeMaterial:
    return writer.episode_material(s, form.episode_id, form.keywords)


@db_step
def save_episode(s: Session, form: WrittenForm) -> None:
    writer.save_episode(s, form.episode_id, form.draft, form.ideas)


@db_step
def framing_targets(s: Session, form: RowId) -> SummaryTargets:
    return framer.framing_targets(s, form.id)


@db_step
def frame_material(s: Session, form: RowId) -> EpisodeFrameMaterial:
    return framer.frame_material(s, form.id)


@db_step
def save_frame_draft(s: Session, form: FrameForm) -> None:
    framer.save_frame_draft(s, form.episode_id, form.draft, form.start)


@db_step
def revision_targets(s: Session, form: RowId) -> SummaryTargets:
    return reviser.revision_targets(s, form.id)


@db_step
def revision_material(s: Session, form: RowId) -> EpisodeRevisionMaterial:
    return reviser.revision_material(s, form.id)


@db_step
def save_revision(s: Session, form: RevisionForm) -> None:
    reviser.save_revision(s, form.episode_id, form.draft, form.instruction)


@db_step
def save_plot(s: Session, form: PlotForm) -> None:
    plot_completer.save_plot(s, form.episode_id, form.plot_text)


@db_step
def known_locations(s: Session, form: LocationScope) -> list[LocationMaterial]:
    return plot_completer.known_locations(s, form.location_id)


@db_step
def add_cast_member(s: Session, form: CastMemberForm) -> None:
    plot_completer.add_cast_member(s, form.episode_id, form.character_id)


@db_step
def add_location(s: Session, form: NewLocationForm) -> None:
    plot_completer.add_location(s, form.episode_id, form.candidate, form.parent_id)


@db_step
def commit_episode(s: Session, form: EpisodeCommitForm) -> EpisodeRecord:
    return CommitEpisode(form).execute(s)


@db_step
def episode_record(s: Session, form: RowId) -> EpisodeRecord:
    return record_of(s, EpisodeRecord, s.get_one(Episode, form.id))
