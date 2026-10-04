#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.knowledge import KnowledgeSerialized, knowledge_of
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode_session.turns import actor_time
from data_access_logic.query import common_query
from db.schema import Episode


class ReadKnowledge(SessionEntrypoint):
    """人物役が、話のセッションでいる時刻に知ることのできるデータを読む。本文・来歴は、公開のものと、その人物が知る人に入ったものだけ。
    アイデアは、知っているもののうち、話のプロットに名前が出るものだけ(ほかは `ReadKnownIdeas` で語から引く)。
    時刻は人物役に渡さないので、その人物の一番新しい手番の行(無ければ話)から取る。"""

    def __init__(self, episode_id: int, character_id: int):
        self.episode_id = episode_id
        self.character_id = character_id

    def execute(self, s: Session) -> KnowledgeSerialized:
        plot_text = common_query.get_row(s, Episode, self.episode_id).plot_text or ""
        return knowledge_of(s, self.character_id, actor_time(s, self.episode_id, self.character_id), plot_text)
