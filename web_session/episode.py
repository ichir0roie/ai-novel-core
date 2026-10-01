#!/usr/bin/env python3
"""話の生成・推敲・プロット補完・概要の作り直しと、Claude が自分で書くための材料の読み出しを、API 越しに回す。

引数は `data_access_logic/episode/` の入口(`GenerateEpisode` など)と同じ。db の段は `data_access_logic/episode/steps.py`、
AI の段は `writer` / `framer` / `reviser` / `plot_completer` の `*_draft`。
AI の呼び出しの前に下書きを枠として保存し、AI の結果は得たその場で書き戻す(途中で落ちても、それまでの分は残す)。
"""
from __future__ import annotations

import logging
import random

from ai.claude_code import ai_client
from ai.claude_code.ai_client import EPISODE_EFFORT, EPISODE_MODEL, PLOT_EFFORT, PLOT_MODEL
from data_access_logic.ai_client import AIClient
from data_access_logic.character.form import CharacterForm
from data_access_logic.episode import caster, framer, plot_completer, reviser, writer
from data_access_logic.episode import steps as episode_steps
from data_access_logic.episode.form import EpisodeForm
from data_access_logic.episode.models import EpisodeBriefSerialized, EpisodeCharacterCandidateDraft, EpisodeMaterial
from data_access_logic.episode.record import EpisodeRecord, EpisodeSummaryRecord
from data_access_logic.idea.search import keywords_of
from data_access_logic.step import RowId
from data_access_logic.style_preference import steps as style_steps
from data_access_logic.style_preference.extras import StyleExtras
from data_access_logic.style_preference.form import StyleTarget
from db.stamp import Stamp
from web_session import character
from web_session.api import call
from web_session.summary import refresh, rewrite_episode_summaries

logger = logging.getLogger(__name__)


def _frame(ai: AIClient, episode_id: int) -> None:
    refresh(ai, call(episode_steps.framing_targets, RowId(id=episode_id)))
    material = call(episode_steps.frame_material, RowId(id=episode_id))
    draft = framer.frame_draft(ai, material)
    call(episode_steps.save_frame_draft, episode_steps.FrameForm(
        episode_id=episode_id, draft=draft, start=framer.frame_start(material, draft)))


def _material(ai: AIClient, episode_id: int) -> EpisodeMaterial:
    """本文・プロットを書く材料。AI が洗い出した語から足した候補のアイデアは、材料を読む段で確定する。"""
    targets = call(episode_steps.writing_targets, RowId(id=episode_id))
    refresh(ai, targets)
    return call(episode_steps.episode_material, episode_steps.MaterialForm(
        episode_id=episode_id, keywords=keywords_of(targets.plot_text, ai, targets.start)))


def _add_characters(
    ai: AIClient, episode_id: int, candidates: list[EpisodeCharacterCandidateDraft], location_id: int | None, time: Stamp,
    plot_text: str,
) -> None:
    rng = random.Random()
    for candidate in candidates:
        # 人物は一人ごとに書き戻すので、途中で止まっても作った人物は残る
        record = character.generate(ai, rng, location_id, time, True,
                                    CharacterForm(name=candidate.called, text=candidate.text), plot_text)
        if record is None:
            logger.warning(f"「{candidate.called}」の人物が得られなかったので足さない")
            continue
        call(episode_steps.add_cast_member, episode_steps.CastMemberForm(episode_id=episode_id, character_id=record.id))


def _cast(ai: AIClient, episode_id: int) -> None:
    """本文を書く前に、プロットで台詞・行動のある人物を登場人物に足す(`caster.cast_from_plot` に当たる)。"""
    material = call(episode_steps.cast_material, RowId(id=episode_id))
    draft = caster.cast_draft(ai, material, PLOT_MODEL, PLOT_EFFORT)
    if draft is None:
        return
    found, created = caster.split_members(material, draft)
    for character_id in found:
        call(episode_steps.add_cast_member, episode_steps.CastMemberForm(episode_id=episode_id, character_id=character_id))
    location_id = material.locations[-1].id if material.locations else None
    _add_characters(ai, episode_id, created, location_id, material.main_episode.start, material.main_episode.plot_text)


def _style_extras(shared_style_extra: str | None, style_extra: str | None) -> StyleExtras:
    extras = call(style_steps.style_extras, style_steps.StyleTargetForm(target=StyleTarget.EPISODE))
    return extras.overridden(shared_style_extra, style_extra)


def _record(episode_id: int) -> EpisodeRecord:
    return call(episode_steps.episode_record, RowId(id=episode_id))


def generate_episode(
    episode: EpisodeForm,
    shared_style_extra: str | None = None,
    style_extra: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    ai: AIClient = ai_client,
) -> EpisodeRecord:
    """`GenerateEpisode` に当たる。プロットか時刻が枠に無ければ、先に枠を決めてから本文を書く。"""
    saved = call(episode_steps.save_episode_frame, episode)
    if saved.needs_frame:
        _frame(ai, saved.id)
    _cast(ai, saved.id)
    material = _material(ai, saved.id)
    extras = _style_extras(shared_style_extra, style_extra)
    draft = writer.episode_draft(ai, material, model or EPISODE_MODEL, effort or EPISODE_EFFORT, extras.shared, extras.own)
    if draft is None:
        raise ValueError("本文が得られなかった")
    call(episode_steps.save_episode, episode_steps.WrittenForm(
        episode_id=saved.id, draft=draft, ideas=material.ideas.linked))
    # 書いた本文から概要を作り直す
    rewrite_episode_summaries(ai, [saved.id])
    return _record(saved.id)


def generate_frame(frame: EpisodeForm, character_ids: list[int] | None = None, ai: AIClient = ai_client) -> EpisodeRecord:
    """`GenerateFrame` に当たる。"""
    form = frame.model_copy()
    if character_ids is not None:
        form.character_ids = character_ids
    saved = call(episode_steps.save_episode_frame, form)
    _frame(ai, saved.id)
    return _record(saved.id)


def revise_episode(
    episode: EpisodeForm,
    instruction: str,
    character_ids: list[int] | None = None,
    model: str | None = None,
    effort: str | None = None,
    shared_style_extra: str | None = None,
    style_extra: str | None = None,
    ai: AIClient = ai_client,
) -> EpisodeRecord:
    """`ReviseEpisode` に当たる。"""
    if episode.id is None:
        raise ValueError("episode.id は必須")
    if not instruction.strip():
        raise ValueError("instruction(直す指示)が空")
    form = episode.model_copy()
    if character_ids is not None:
        form.character_ids = character_ids
    call(episode_steps.save_episode_frame, form)
    refresh(ai, call(episode_steps.revision_targets, RowId(id=episode.id)))
    material = call(episode_steps.revision_material, RowId(id=episode.id))
    extras = _style_extras(shared_style_extra, style_extra)
    draft = reviser.revision_draft(
        ai, material, instruction, model or EPISODE_MODEL, effort or EPISODE_EFFORT, extras.shared, extras.own)
    if draft is None:
        raise ValueError("本文が得られなかった")
    call(episode_steps.save_revision, episode_steps.RevisionForm(
        episode_id=episode.id, draft=draft, instruction=instruction))
    rewrite_episode_summaries(ai, [episode.id])
    return _record(episode.id)


def complete_plot(
    episode: EpisodeForm, order: str | None = None, model: str | None = None, effort: str | None = None,
    ai: AIClient = ai_client,
) -> EpisodeRecord:
    """`CompletePlot` に当たる。プロットを書き直し、プロットに出るのに材料に無い人物・舞台を足す。"""
    model, effort = model or PLOT_MODEL, effort or PLOT_EFFORT
    saved = call(episode_steps.save_episode_frame, episode)
    if saved.needs_frame:
        _frame(ai, saved.id)
    material = _material(ai, saved.id)
    plot_text = plot_completer.plot_draft(ai, material, order or None, model, effort)
    call(episode_steps.save_plot, episode_steps.PlotForm(episode_id=saved.id, plot_text=plot_text))

    location_id = material.locations[-1].id if material.locations else None
    known = call(episode_steps.known_locations, episode_steps.LocationScope(location_id=location_id))
    known_people = call(episode_steps.known_characters, episode_steps.KnownCharactersForm(
        episode_id=saved.id, time=material.main_episode.start))
    casting = plot_completer.casting_draft(ai, material, plot_text, known, known_people, model, effort)
    if casting is not None and casting.characters:
        _add_characters(ai, saved.id, casting.characters, location_id, material.main_episode.start, plot_text)
    if casting is not None and casting.location is not None:
        call(episode_steps.add_location, episode_steps.NewLocationForm(
            episode_id=saved.id, candidate=casting.location, parent_id=location_id))
    logger.info(f"{material.story.name} 話 id={saved.id} のプロットを補完した")
    return _record(saved.id)


def read_episode_brief(episode_id: int, ai: AIClient = ai_client) -> EpisodeBriefSerialized:
    """`ReadEpisodeBrief` に当たる。"""
    refresh(ai, call(episode_steps.brief_targets, RowId(id=episode_id)))
    return EpisodeBriefSerialized.model_validate(call(episode_steps.episode_brief, RowId(id=episode_id)))


def rewrite_episode_summary(episode_ids: list[int], ai: AIClient = ai_client) -> list[EpisodeSummaryRecord]:
    """`RewriteEpisodeSummary` に当たる。本文が変わっていなくても概要を作り直す。"""
    return rewrite_episode_summaries(ai, episode_ids, stale_only=False)
