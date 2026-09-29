#!/usr/bin/env python3
"""本文は書かない(`writer.write_episode` で別に書く)。"""
from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.time_keeper import constants
from ai.time_keeper._ai import AIClient
from ai.time_keeper._format import format_time
from data_access_logic.character.cast import cast_at
from data_access_logic.episode.models import (
    EpisodeFrameDraft, EpisodeFrameMaterial, EpisodeFrameMaterialSerialized, FrameEpisode, StoryMaterial,
)
from data_access_logic.episode.summary import past_episodes
from data_access_logic.event.summary import summarized_events
from data_access_logic.location.models import LocationMaterial
from data_access_logic.query import common_query
from db.schema import Episode, EpisodeCharacter
from db.stamp import Stamp, StampError

_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの構成を考える作家です。
作品・直前の話・登場人物・作者の指定を日本語の見出しを付けた JSON で渡すので、この作品の次の一話の枠(題・種・時刻)を決めてください。
種は本文を書く前の作者のメモです。300〜500 字を目安に、「## 場面」(番号付きの箇条書き。一行は「場所 / 出る人 / そこで変わること」)と「## 狙い」(この話で読者に伝えたいこと・変わること)の二つの節で書いてください。
視点・場所を作者が指定したときは、それに沿う場面にしてください(視点・場所自体はここでは決めません)。
直前の話は概要で渡します。その続きとして自然に立つ話にし、直前の話をなぞり直さないでください。
「この時点より後に既に決まっている出来事」は、それと矛盾させず、そこで起きることを先回りしないでください。
作者の指定は、それを核にして足りないところを補ってください。null でない値は決まっているので変えないでください。
時刻は「年/月/日」の形で、直前の話より後、作品の期間の中から選んでください。"""


def _frame_material(s: Session, ai: AIClient, episode_id: int, past_episode_count: int) -> EpisodeFrameMaterial:
    episode = s.scalar(
        select(Episode)
        .where(Episode.id == episode_id)
        .options(
            joinedload(Episode.story),
            joinedload(Episode.place),
            joinedload(Episode.viewpoint_character),
            selectinload(Episode.episode_characters).joinedload(EpisodeCharacter.character),
        )
        .execution_options(populate_existing=True)
    )
    if episode is None:
        raise ValueError(f"話 id={episode_id} が見つからない")
    # 要約の commit で読み込んだ関連が期限切れになるので、AI を呼ぶ前にマテリアルへ写しておく
    main_episode = FrameEpisode.model_validate(episode)
    story = StoryMaterial.model_validate(episode.story)
    place_id = episode.story.place_id
    characters = [link.character for link in episode.episode_characters]

    previous = past_episodes(s, ai, episode, past_episode_count)
    # 時刻が決まっていなければ、直前の話の時点の人物・出来事を材料にする
    time = main_episode.start or (previous[0].start if previous else None) or story.start or Stamp(1)
    return EpisodeFrameMaterial(
        story=story,
        main_episode=main_episode,
        past_episodes=previous,
        locations=[LocationMaterial.model_validate(step) for step in common_query.place_path(s, place_id)]
        if place_id is not None else [],
        cast=cast_at(s, ai, characters, time),
        later_events=summarized_events(
            s, ai,
            common_query.events_after_select(
                place_id, [character.id for character in characters], time, limit=constants.LATER_EVENT_LIMIT)),
    )


def frame_episode(
    s: Session, ai: AIClient, episode_id: int, past_episode_count: int = constants.EPISODE_PREVIOUS_LIMIT,
) -> Episode:
    """題・種は作者の指定を核に AI が組み立て直し、時刻は決まっていればそれ、無ければ AI が直前の話の後から選ぶ。"""
    material = _frame_material(s, ai, episode_id, past_episode_count)

    prompt = "\n".join([
        EpisodeFrameMaterialSerialized.model_validate(material).model_dump_json(indent=2),
        "この作品の次の一話の枠を決めてください。",
    ])
    decided = ai.try_generate_json(prompt, EpisodeFrameDraft.model_json_schema(), system=_SYSTEM_PROMPT)
    try:
        draft = EpisodeFrameDraft.model_validate(decided)
    except ValidationError as error:
        raise ValueError(f"枠が得られなかった: {error}") from error

    start = material.main_episode.start
    if start is None:
        try:
            start = Stamp.parse(draft.start)
        except StampError:
            start = None
    if start is None:
        raise ValueError(f"時刻が決まらなかった(AI の答え: {draft.start!r})。start を渡す")

    record = s.get_one(Episode, episode_id)
    record.title = draft.title
    record.key = draft.key
    record.start = start
    record.synced = False
    s.commit()
    print(f"[data_access_logic/episode] {material.story.name} {format_time(start)}「{record.title}」"
          f" id={record.id} の枠を決めた")
    return record
