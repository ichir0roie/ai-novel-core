#!/usr/bin/env python3
"""本文は書かない(本文はスキル `episode` でこのセッションの Claude が書く)。

db だけの段(`framing_targets` → 要約を揃える → `frame_material` → `save_frame_draft`)と、AI だけの段(`frame_draft`)に分けてある。
流れ(`data_access_logic/flows/episode.py`)がつなぐ。
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.mentioned import MENTIONED_INSTRUCTION
from ai.instructions.past_episodes import PAST_EPISODES_INSTRUCTION
from ai.instructions.plot import PLOT_FORMAT_INSTRUCTION
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import cast_of, mentioned_of, relations_at
from data_access_logic.episode.material import episode_location_id, later_events_select, load_episode, summary_targets_of
from data_access_logic.episode.models import (
    EpisodeFrameDraft, EpisodeFrameMaterial, EpisodeFrameMaterialSerialized, FrameEpisode, StoryMaterial,
)
from data_access_logic.episode.mentions import cast_characters, mentioned_in, save_mentions
from data_access_logic.episode.summary import latest_past_episode, past_episodes
from data_access_logic.event.summary import events_of
from data_access_logic.query import common_query
from data_access_logic.summary_targets import SummaryTargets
from db.schema import Episode
from db.stamp import Stamp, StampError

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = f"""\
あなたは日本語のライトノベルの構成を考える作家です。
作品・前の話・登場人物・作者の指定を日本語の見出しを付けた JSON で渡すので、この作品の次の一話の枠(題・プロット・時刻)を決めてください。
{PLOT_FORMAT_INSTRUCTION}
作者の指定の題・プロットは核にして、足りないところを補って書き直してください(プロットにある出来事・人物・狙いは落とさない)。
作者の指定の時刻・視点・場所は、null でなければ決まっているので変えず、それに沿う場面にしてください(視点・場所自体はここでは決めません)。
時刻が決まっていなければ、「年/月/日」の形で、直前の話より後から選んでください。決まっていれば start は null にしてください。
前の話は概要で古い順に渡します。その続きとして自然に立つ話にし、直前の話をなぞり直さないでください。
「この時点より後に既に決まっている出来事」は、それと矛盾させず、そこで起きることを先回りしないでください。
{PAST_EPISODES_INSTRUCTION}
{EVENT_AGE_INSTRUCTION}
{MENTIONED_INSTRUCTION}"""


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
    story_location_id = episode.story.location_id
    characters = cast_characters(episode)
    time = _time(s, episode)
    return EpisodeFrameMaterialSerialized(
        story=StoryMaterial.model_validate(episode.story),
        main_episode=FrameEpisode.model_validate(episode),
        past_episodes=past_episodes(s, episode, characters),
        locations=common_query.location_path(s, story_location_id) if story_location_id is not None else [],
        cast=cast_of(s, characters, time),
        mentioned=mentioned_of(mentioned_in(episode), time),
        relations=relations_at(s, characters, time),
        later_events=events_of(s, later_events_select(episode_location_id(episode), characters, time)),
    )


def frame_draft(ai: AIClient, material: EpisodeFrameMaterial) -> EpisodeFrameDraft:
    prompt = "\n".join([
        EpisodeFrameMaterialSerialized.model_validate(material).model_dump_json(indent=2),
        "この作品の次の一話の枠を決めてください。",
    ])
    draft = ai.generate(prompt, EpisodeFrameDraft, system=_SYSTEM_PROMPT)
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
    record.synced = False
    s.flush()
    save_mentions(s, episode_id)
    logger.info(f"{start}「{record.title}」 id={record.id} の枠を決めた")
    return record
