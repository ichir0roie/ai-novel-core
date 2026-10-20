#!/usr/bin/env python3
"""話の db の段(`data_access_logic/step.py`)。流れ(`data_access_logic/flows/`)が、手元では自分のセッションで、web のセッションでは API 越しに呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai.instructions.style import layout_novel_text
from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode import brief, framer, material, moves, plot_completer, relations, voices
from data_access_logic.episode.moves import EpisodeMovesMaterial
from data_access_logic.episode.relations import EpisodeRelationsMaterial, RelationsForm
from data_access_logic.character.record import CharacterRelationRecord
from data_access_logic.character.models import MentionedMaterial
from data_access_logic.episode.form import EpisodeCommitForm, EpisodeForm, EpisodeReviseForm, has_cast, save_frame, set_characters
from data_access_logic.episode.mentions import save_mentions
from data_access_logic.episode.models import (
    EpisodeBrief, EpisodeFrameDraft, EpisodeFrameMaterial, EpisodeLocationCandidateDraft,
    EpisodeMaterial,
)
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.episode.voices import VoiceForm, VoiceSource
from data_access_logic.idea.models import IdeaDraft
from data_access_logic.location.models import LocationMaterial
from data_access_logic.step import RowId, db_step
from data_access_logic.summary_targets import SummaryTargets
from data_access_logic.query import common_query
from db.schema import Character, Episode, Location, Story
from db.stamp import Stamp


class SavedFrame(BaseModel):
    id: int
    # プロットか時刻が空なので、本文を書く前に枠を決める
    needs_frame: bool
    # 登場人物(名前だけ出る人物でない行)がいるか
    has_cast: bool


class MaterialForm(BaseModel):
    episode_id: int
    # 話のプロットから AI が挙げた、アイデアと照らす語
    keywords: list[IdeaDraft]


class BriefForm(BaseModel):
    episode_id: int
    # プロット・話のセッションの行・今の本文から AI が挙げた、アイデアと照らす語
    keywords: list[IdeaDraft]


class FrameForm(BaseModel):
    episode_id: int
    draft: EpisodeFrameDraft
    start: Stamp


class PlotForm(BaseModel):
    episode_id: int
    plot_text: str


class LocationScope(BaseModel):
    location_id: int | None


class KnownCharactersForm(BaseModel):
    episode_id: int
    # 年齢・その時点の口調などを決める時刻(話の時刻)
    time: Stamp


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
    return SavedFrame(id=record.id, needs_frame=not record.plot_text.strip() or record.start is None,
                      has_cast=has_cast(s, record.id))


@db_step
def writing_targets(s: Session, form: RowId) -> material.WritingTargets:
    return material.writing_targets(s, form.id)


@db_step
def episode_material(s: Session, form: MaterialForm) -> EpisodeMaterial:
    return material.episode_material(s, form.episode_id, form.keywords)


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
def voice_sources(s: Session, form: RowId) -> list[VoiceSource]:
    return voices.voice_sources(s, form.id)


@db_step
def write_voices(s: Session, form: VoiceForm) -> list[int]:
    return voices.write_voices(s, form.episode_id, form.voices)


@db_step
def brief_targets(s: Session, form: RowId) -> brief.BriefTargets:
    return brief.brief_targets(s, form.id)


@db_step
def episode_brief(s: Session, form: BriefForm) -> EpisodeBrief:
    return brief.episode_brief(s, form.episode_id, form.keywords)


@db_step
def save_plot(s: Session, form: PlotForm) -> None:
    plot_completer.save_plot(s, form.episode_id, form.plot_text)


@db_step
def known_locations(s: Session, form: LocationScope) -> list[LocationMaterial]:
    return material.known_locations(s, form.location_id)


@db_step
def known_characters(s: Session, form: KnownCharactersForm) -> list[MentionedMaterial]:
    return plot_completer.known_characters(s, form.episode_id, form.time)


@db_step
def add_cast_member(s: Session, form: CastMemberForm) -> None:
    plot_completer.add_cast_member(s, form.episode_id, form.character_id)


@db_step
def add_location(s: Session, form: NewLocationForm) -> None:
    plot_completer.add_location(s, form.episode_id, form.candidate, form.parent_id)


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
    if form.main_text is not None:
        record.main_text = layout_novel_text(form.main_text)
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
def moves_material(s: Session, form: RowId) -> EpisodeMovesMaterial | None:
    return moves.moves_material(s, form.id)


@db_step
def relations_material(s: Session, form: RowId) -> EpisodeRelationsMaterial | None:
    return relations.relations_material(s, form.id)


@db_step
def add_relations(s: Session, form: RelationsForm) -> list[CharacterRelationRecord]:
    return relations.add_relations(s, form)
