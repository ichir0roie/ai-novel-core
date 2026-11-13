#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode import brief
from data_access_logic.episode.models import CastEpisodesSerialized


class ReadCastEpisodes(SessionEntrypoint):
    """人物たち(`character_ids`。省けば話の登場人物と名前だけ出る人物)が、話(`episode_id`)より前に関わった話
    (作品を問わない)のうち、人物ごとに直近の数話(`constants.EPISODE_RECENT_APPEARANCE_COUNT`)を、話ごとにまとめて
    古い順に読む。本文は、どれかの人物の一番新しい話にだけ付く(ほかは題・時刻・出た人物だけ)。プロットは返さない。
    語り部が登場人物のこれまでを掴むのに使う。
    """

    def __init__(self, episode_id: int, character_ids: list[int] | None = None):
        self.episode_id = episode_id
        self.character_ids = character_ids

    def execute(self, s: Session) -> CastEpisodesSerialized:
        return brief.cast_episodes(s, self.episode_id, self.character_ids)
