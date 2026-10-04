#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode_session.record import SessionIdeas
from data_access_logic.idea.classification import classification_kinds
from data_access_logic.idea.context import resolve_ideas
from data_access_logic.idea.models import IdeaDraft
from data_access_logic.query import common_query
from db.schema import Episode


class AddIdeas(CommitEntrypoint):
    """話に出た新しい語を、話の場所・時刻でアイデアと照らし、当たらなかった語を候補のアイデアとして足す。
    語り部(と、話を書く Claude)が、場面に新しく出した固有の語を足していくための口。本文は返さず、名前だけを返す。
    種別は、話の場所の世界にある分類から選ばせる(無い種別を渡すと、同じものをまとめる分類が別にできる)。"""

    def __init__(self, episode_id: int, ideas: list[IdeaDraft]):
        self.episode_id = episode_id
        self.ideas = ideas

    def execute(self, s: Session) -> SessionIdeas:
        episode = common_query.get_row(s, Episode, self.episode_id)
        kinds = classification_kinds(s, episode.location_id)
        if kinds is not None:
            unknown = [idea.kind for idea in self.ideas if idea.kind not in kinds]
            if unknown:
                raise ValueError(f"種別 {'・'.join(dict.fromkeys(unknown))} の分類が無い。種別は次から選ぶ: {'・'.join(kinds)}")
        added = [idea.name for idea in resolve_ideas(s, self.ideas, episode.location_id, episode.start).candidates]
        return SessionIdeas(added=added, kept=[idea.keyword for idea in self.ideas if idea.keyword not in added])
