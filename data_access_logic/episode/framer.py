#!/usr/bin/env python3
"""本文は書かない(本文はスキル `episode` でこのセッションの Claude が書く)。

db だけの段(`framing_targets` → 要約を揃える → `frame_material` → `save_frame_draft`)と、AI だけの段(`frame_draft`)に分けてある。
流れ(`data_access_logic/flows/episode.py`)がつなぐ。
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ai.instructions.materials import LATER_EVENTS_NOTE, MENTIONED_NOTE, TIME_NOTE
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import cast_of, mentioned_of, relations_at
from data_access_logic.episode.material import later_events_select, load_episode, summary_targets_of
from data_access_logic.episode.models import (
    EpisodeFrameDraft, EpisodeFrameMaterial, EpisodeFrameMaterialSerialized, FrameEpisode, StoryMaterial,
)
from data_access_logic.episode.mentions import cast_characters, mentioned_in, save_mentions
from data_access_logic.episode.past import latest_past_episode
from data_access_logic.event.summary import events_of
from data_access_logic.query import common_query
from data_access_logic.summary_targets import SummaryTargets
from db.schema import Episode, StyleScope
from db.stamp import Stamp, StampError

logger = logging.getLogger(__name__)

_SYSTEM = f"""\
作品・登場人物・作者の指定を渡すので、この作品の次の一話の枠(題・プロット・時刻)を決める。
作者の指定の題・プロットは核にし、プロットにある出来事・人物・狙いは落とさない。
作者の指定の時刻・視点・場所は、null でなければ変えずに沿う。視点・場所自体はここでは決めない。
時刻が決まっていなければ、直前の話より後から選ぶ。
作品の筋書きと、登場人物の来歴・関係が、この話の前までの筋。済んだことをなぞり直さない。

{LATER_EVENTS_NOTE}

{MENTIONED_NOTE}

{TIME_NOTE}"""


def _time(s: Session, episode: Episode) -> Stamp:
    """時刻が決まっていなければ、直前の話の時点の人物・出来事を材料にする。"""
    if episode.start is not None:
        return episode.start
    latest = latest_past_episode(s, episode)
    return (latest.start if latest is not None else None) or Stamp(1)


def _unwritten(s: Session, episode_id: int) -> Episode:
    episode = load_episode(s, episode_id)
    FrameEpisode.model_validate(episode)
    return episode


def framing_targets(s: Session, episode_id: int) -> SummaryTargets:
    episode = _unwritten(s, episode_id)
    return summary_targets_of(s, episode, _time(s, episode), with_location_events=False)


def frame_material(s: Session, episode_id: int) -> EpisodeFrameMaterialSerialized:
    """要約は揃えてある前提でそのまま読む。"""
    episode = _unwritten(s, episode_id)
    characters = cast_characters(episode)
    time = _time(s, episode)
    return EpisodeFrameMaterialSerialized(
        story=StoryMaterial.model_validate(episode.story),
        main_episode=FrameEpisode.model_validate(episode),
        locations=common_query.location_path(s, episode.location_id) if episode.location_id is not None else [],
        cast=cast_of(s, characters, time),
        mentioned=mentioned_of(mentioned_in(episode), time),
        relations=relations_at(s, characters, time),
        later_events=events_of(s, later_events_select(episode.location_id, characters, time)),
    )


def frame_draft(ai: AIClient, material: EpisodeFrameMaterial) -> EpisodeFrameDraft:
    prompt = "\n".join([
        EpisodeFrameMaterialSerialized.model_validate(material).model_dump_json(indent=2),
        "この作品の次の一話の枠を決める。",
    ])
    draft = ai.generate(prompt, EpisodeFrameDraft, system=_SYSTEM, style_scope=StyleScope.PLOT)
    if draft is None:
        raise ValueError("枠が得られなかった")
    return draft


def frame_start(material: EpisodeFrameMaterial, draft: EpisodeFrameDraft) -> Stamp:
    """時刻は決まっていればそれ、無ければ AI が直前の話の後から選んだもの。"""
    start = material.main_episode.start
    if start is None:
        try:
            start = Stamp.parse(draft.start)
        except StampError:
            start = None
    if start is None:
        raise ValueError(f"時刻が決まらなかった(AI の答え: {draft.start!r})。start を渡す")
    return start


def save_frame_draft(s: Session, episode_id: int, draft: EpisodeFrameDraft, start: Stamp) -> Episode:
    record = s.get_one(Episode, episode_id)
    record.title = draft.title
    record.plot_text = draft.plot_text
    record.start = start
    s.flush()
    save_mentions(s, episode_id)
    logger.info(f"{start}「{record.title}」 id={record.id} の枠を決めた")
    return record
