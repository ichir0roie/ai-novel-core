#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.knowledge import KnowledgeSerialized, knowledge_of
from data_access_logic.episode_session.turns import knowing_time
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.query import common_query
from db.schema import Episode
from db.stamp import Stamp


class ReadKnowledge(SessionEntrypoint):
    """人物役が、話のセッションでいる時刻に知ることのできるデータを読む。本文・来歴は、その人物が知る相手に入ったものだけ。
    アイデアは、知っているもののうち、話のプロットに名前が出るものだけ(ほかは `ReadKnownIdeas` で語から引く)。
    時刻は人物役に渡さないので、その人物の一番新しい手番の行(無ければ話)から取る。
    話を渡さず `time` だけを渡せば、その時刻で読む(スキル `call-character` で歳を言って呼ぶとき)。プロットが無いので、アイデアは入らない。"""

    def __init__(self, character_id: int, episode_id: int | None = None, time: Stamp | str | None = None):
        self.character_id = character_id
        self.episode_id = episode_id
        self.time = time

    def execute(self, s: Session) -> KnowledgeSerialized:
        plot_text = ""
        if self.episode_id is not None:
            plot_text = common_query.get_row(s, Episode, self.episode_id).plot_text or ""
        return knowledge_of(s, self.character_id, knowing_time(s, self.character_id, self.episode_id, self.time), plot_text)
