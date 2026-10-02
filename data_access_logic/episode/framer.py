#!/usr/bin/env python3
"""本文は書かない(本文はスキル `episode` でこのセッションの Claude が書く)。

db だけの段(`framing_targets` → 要約を揃える → `frame_material` → `save_frame_draft`)と、AI だけの段(`frame_draft`)に分けてある。
手元では `frame_episode` がつなぎ、web のセッションでは `web_session/episode.py` が API 越しにつなぐ。
"""
from __future__ import annotations

import logging

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions.mentioned import MENTIONED_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import cast_event_ids, cast_of, mentioned_of, relations_at
from data_access_logic.episode.models import (
    EpisodeFrameDraft, EpisodeFrameMaterial, EpisodeFrameMaterialSerialized, FrameEpisode, StoryMaterial,
)
from data_access_logic.episode.mentions import cast_characters, mentioned_in, save_mentions
from data_access_logic.episode.summary import latest_past_episode, past_episode_ids, past_episodes
from data_access_logic.event.summary import events_of
from data_access_logic.query import common_query
from data_access_logic.summary_targets import SummaryTargets, refresh
from db.schema import Episode, EpisodeCharacter, Event
from db.stamp import Stamp, StampError

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = f"""\
あなたは日本語のライトノベルの構成を考える作家です。
作品・前の話・登場人物・作者の指定を日本語の見出しを付けた JSON で渡すので、この作品の次の一話の枠(題・プロット・時刻)を決めてください。
プロットは本文を書く前の作者のメモです。300〜500 字を目安に、「## 場面」(番号付きの箇条書き。一行は「場所 / 出る人 / そこで変わること」)と「## 狙い」(この話で読者に伝えたいこと・変わること)の二つの節で書いてください。
視点・場所を作者が指定したときは、それに沿う場面にしてください(視点・場所自体はここでは決めません)。
前の話は概要で古い順に渡します。その続きとして自然に立つ話にし、直前の話をなぞり直さないでください。
「この時点より後に既に決まっている出来事」は、それと矛盾させず、そこで起きることを先回りしないでください。
作者の指定は、それを核にして足りないところを補ってください。null でない値は決まっているので変えないでください。
時刻は「年/月/日」の形で、直前の話より後、作品の期間の中から選んでください。
{MENTIONED_INSTRUCTION}"""


def _episode(s: Session, episode_id: int) -> Episode:
    episode = s.scalar(
        select(Episode)
        .where(Episode.id == episode_id)
        .options(
            joinedload(Episode.story),
            joinedload(Episode.location),
            joinedload(Episode.viewpoint_character),
            selectinload(Episode.episode_characters).joinedload(EpisodeCharacter.character),
        )
        .execution_options(populate_existing=True)
    )
    if episode is None:
        raise ValueError(f"話 id={episode_id} が見つからない")
    return episode


def _time(s: Session, episode: Episode) -> Stamp:
    """時刻が決まっていなければ、直前の話の時点の人物・出来事を材料にする。"""
    if episode.start is not None:
        return episode.start
    latest = latest_past_episode(s, episode)
    return (latest.start if latest is not None else None) or episode.story.start or Stamp(1)


def _later_events_select(episode: Episode, time: Stamp) -> Select[Event]:
    return common_query.events_after_select(
        episode.story.location_id, [character.id for character in cast_characters(episode)], time,
        limit=constants.LATER_EVENT_LIMIT)


def framing_targets(s: Session, episode_id: int) -> SummaryTargets:
    episode = _episode(s, episode_id)
    time = _time(s, episode)
    return SummaryTargets(
        episode_ids=past_episode_ids(s, episode, cast_characters(episode)),
        event_ids=[*cast_event_ids(s, cast_characters(episode), time),
                   *(event.id for event in s.scalars(_later_events_select(episode, time)).all())],
    )


def frame_material(s: Session, episode_id: int) -> EpisodeFrameMaterialSerialized:
    """要約は揃えてある前提でそのまま読む。"""
    episode = _episode(s, episode_id)
    location_id = episode.story.location_id
    characters = cast_characters(episode)
    time = _time(s, episode)
    return EpisodeFrameMaterialSerialized(
        story=StoryMaterial.model_validate(episode.story),
        main_episode=FrameEpisode.model_validate(episode),
        past_episodes=past_episodes(s, episode, characters),
        locations=common_query.location_path(s, location_id) if location_id is not None else [],
        cast=cast_of(s, characters, time),
        mentioned=mentioned_of(mentioned_in(episode), time),
        relations=relations_at(s, characters, time),
        later_events=events_of(s, _later_events_select(episode, time)),
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


def frame_episode(s: Session, ai: AIClient, episode_id: int) -> Episode:
    """題・プロットは作者の指定を核に AI が組み立て直し、時刻は決まっていればそれ、無ければ AI が直前の話の後から選ぶ。"""
    refresh(s, ai, framing_targets(s, episode_id))
    material = frame_material(s, episode_id)
    draft = frame_draft(ai, material)
    record = save_frame_draft(s, episode_id, draft, frame_start(material, draft))
    s.commit()
    return record
