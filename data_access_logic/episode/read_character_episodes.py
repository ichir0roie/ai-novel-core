#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode import brief
from data_access_logic.episode.models import CharacterEpisodesSerialized


class ReadCharacterEpisodes(SessionEntrypoint):
    """人物(`character_id`)が、話(`episode_id`)より前に関わった話(作品を問わない)のうち、直近の数話
    (`constants.EPISODE_RECENT_APPEARANCE_COUNT`)を本文つきで読む(プロットは返さない)。古い順。
    語り部が登場人物のこれまでを掴むのに、人物ごとに呼ぶ。
    """

    def __init__(self, episode_id: int, character_id: int):
        self.episode_id = episode_id
        self.character_id = character_id

    def execute(self, s: Session) -> CharacterEpisodesSerialized:
        return brief.character_episodes(s, self.episode_id, self.character_id)
