#!/usr/bin/env python3
"""話の枠の生成・プロット補完・概要の作り直しと、Claude が自分で書くための材料の読み出しの流れ。

db の段は `data_access_logic/episode/steps.py`、
AI の段は `framer` / `plot_completer` の `*_draft`。
AI の呼び出しの前に下書きを枠として保存し、AI の結果は得たその場で書き戻す(途中で落ちても、それまでの分は残す)。
"""
from __future__ import annotations

import logging
import random

from ai.claude_code import ai_client
from ai.claude_code.ai_client import EFFORT, MODEL
from data_access_logic.ai_client import AIClient
from data_access_logic.episode import framer, plot_completer, voices
from data_access_logic.episode import steps as episode_steps
from data_access_logic.episode.form import EpisodeForm
from data_access_logic.episode.models import (
    EpisodeBriefSerialized, EpisodeCastingSerialized, EpisodeCharacterCandidateDraft, EpisodeMaterial,
)
from data_access_logic.episode.record import EpisodeRecord, EpisodeSummaryRecord
from data_access_logic.idea.search import keywords_of
from data_access_logic.step import RowId
from db.stamp import Stamp
from data_access_logic.flows import character
from data_access_logic.caller import call
from data_access_logic.flows.summary import refresh, rewrite_episode_summaries

logger = logging.getLogger(__name__)


def _frame(ai: AIClient, episode_id: int) -> None:
    refresh(ai, call(episode_steps.framing_targets, RowId(id=episode_id)))
    material = call(episode_steps.frame_material, RowId(id=episode_id))
    draft = framer.frame_draft(ai, material)
    call(episode_steps.save_frame_draft, episode_steps.FrameForm(
        episode_id=episode_id, draft=draft, start=framer.frame_start(material, draft)))


def _material(ai: AIClient, episode_id: int) -> EpisodeMaterial:
    """プロットを書き直す材料。AI が洗い出した語から足した候補のアイデアは、材料を読む段で確定する。"""
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
                                    plot_completer.character_draft(candidate), plot_text)
        if record is None:
            logger.warning(f"「{candidate.called}」の人物が得られなかったので足さない")
            continue
        call(episode_steps.add_cast_member, episode_steps.CastMemberForm(episode_id=episode_id, character_id=record.id))


def _record(episode_id: int) -> EpisodeRecord:
    return call(episode_steps.episode_record, RowId(id=episode_id))


def generate_frame(frame: EpisodeForm, ai: AIClient = ai_client) -> EpisodeRecord:
    """`GenerateFrame` に当たる。"""
    saved = call(episode_steps.save_episode_frame, frame)
    _frame(ai, saved.id)
    return _record(saved.id)


def complete_plot(
    episode: EpisodeForm, order: str | None = None, model: str | None = None, effort: str | None = None,
    ai: AIClient = ai_client,
) -> EpisodeRecord:
    """`CompletePlot` に当たる。プロットを書き直し、プロットに出るのに材料に無い人物・舞台を足す。"""
    model, effort = model or MODEL, effort or EFFORT
    saved = call(episode_steps.save_episode_frame, episode)
    if not saved.has_cast:
        raise ValueError(f"話 id={saved.id} の登場人物(episode_character)が空。登場人物を指定してから補完する")
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


def read_episode_casting(episode_id: int, ai: AIClient = ai_client) -> EpisodeCastingSerialized:
    """`ReadEpisodeCasting` に当たる。"""
    refresh(ai, call(episode_steps.casting_targets, RowId(id=episode_id)))
    return EpisodeCastingSerialized.model_validate(call(episode_steps.episode_casting, RowId(id=episode_id)))


def refresh_voices(ai: AIClient, episode_id: int) -> None:
    """文体の見本(直前の五話)のセリフから、登場人物の話し方を調整して書き戻す。AI が答えなくても材料は読む。"""
    source = call(episode_steps.voice_source, RowId(id=episode_id))
    if source is None:
        return
    drafts = voices.voice_draft(ai, source)
    if drafts is None:
        logger.warning(f"話 id={episode_id} の登場人物の話し方を調整できなかった(AI が答えなかった)")
        return
    written = call(episode_steps.write_voices, voices.VoiceForm(episode_id=episode_id, voices=drafts.voices))
    if written:
        logger.info(f"話 id={episode_id} の直前の話から、人物 id={written} の話し方を調整した")


def read_episode_brief(episode_id: int, ai: AIClient = ai_client) -> EpisodeBriefSerialized:
    """`ReadEpisodeBrief` に当たる。直前の五話のセリフで登場人物の話し方を調整してから材料を読む。
    設定は、プロット・話のセッションの行・今の本文から AI が挙げた語で引く。語の数を AI が絞るので、元ごとに挙げさせる。"""
    targets = call(episode_steps.brief_targets, RowId(id=episode_id))
    refresh(ai, targets)
    refresh_voices(ai, episode_id)
    keywords = [keyword for text in targets.word_sources for keyword in keywords_of(text, ai, targets.start)]
    return EpisodeBriefSerialized.model_validate(call(episode_steps.episode_brief, episode_steps.BriefForm(
        episode_id=episode_id, keywords=keywords)))


def rewrite_episode_summary(episode_ids: list[int], ai: AIClient = ai_client) -> list[EpisodeSummaryRecord]:
    """`RewriteEpisodeSummary` に当たる。本文が変わっていなくても概要を作り直す。"""
    return rewrite_episode_summaries(ai, episode_ids, stale_only=False)
