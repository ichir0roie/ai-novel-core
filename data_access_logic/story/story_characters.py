#!/usr/bin/env python3
"""作品に出てくる人物(話の登場人物を選ぶ画面の候補)。
章ごとに数えると、足したばかりの章で候補が空になるので、一番上の作品とその子孫(章・外伝)をまとめて数える。
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.query import common_query
from db.schema import Episode, EpisodeCharacter, Event, EventCharacter


def story_character_ids(s: Session, story_id: int) -> list[int]:
    """作品の話の登場人物と出来事の当事者。出てくる回数(話と出来事の数)の多い順、同じ回数は id の順"""
    story_ids = common_query.descendant_story_ids(s, common_query.story_path_ids(s, story_id)[0])
    counts = Counter(s.scalars(
        select(EpisodeCharacter.character_id).join(Episode, Episode.id == EpisodeCharacter.episode_id)
        .where(Episode.story_id.in_(story_ids))).all())
    counts.update(s.scalars(
        select(EventCharacter.character_id).join(Event, Event.id == EventCharacter.event_id)
        .where(Event.story_id.in_(story_ids))).all())
    return sorted(counts, key=lambda character_id: (-counts[character_id], character_id))
