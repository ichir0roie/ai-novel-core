#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode.mentions import named_characters, save_mentions
from db.schema import Episode


class EpisodeMentions(BaseModel):
    id: int
    title: str
    mentioned_character_ids: list[int]


class RefreshMentions(CommitEntrypoint):
    """話に名前だけ出る人物(`episode_character` の `mentioned` の行)を、今のプロット・本文から拾い直す。

    拾い直しは話を保存したときにしか走らないので、その仕組みより前に書いた話や、あとから人物を足した話の取りこぼしを埋めるのに使う。
    `episode_ids` を省けばすべての話。登場人物(`mentioned` でない行)は変えない。
    """


    def __init__(self, episode_ids: list[int] | None = None):
        self.episode_ids = episode_ids

    def execute(self, s: Session) -> list[EpisodeMentions]:
        query = select(Episode.id).order_by(Episode.id)
        if self.episode_ids is not None:
            query = query.where(Episode.id.in_(self.episode_ids))
        characters = named_characters(s)
        refreshed = []
        for episode_id in s.scalars(query).all():
            mentioned_ids = save_mentions(s, episode_id, characters)
            refreshed.append(EpisodeMentions(
                id=episode_id, title=s.get_one(Episode, episode_id).title, mentioned_character_ids=mentioned_ids))
        return refreshed
