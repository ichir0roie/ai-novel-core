#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode.form import set_characters
from data_access_logic.episode.mentions import save_mentions
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.query import common_query
from db.schema import Character, ConfirmStatus, Episode, Location


class CastEpisode(CommitEntrypoint):
    """本文を書く前に、Claude がプロットから決めた登場人物・場所・視点を話に結ぶ。

    登場人物(`episode_character`)は `character_ids` でまるごと置き換え、名前だけ出る人物はプロット・本文から拾い直す。
    登場人物と視点の人物は、この話の本文に書く人物なので承認する(未確認の人物は本文の材料に出せない)。
    `location_id` / `viewpoint_character_id` は渡したときだけ書く。同期フラグ(`synced`)は変えない。
    """

    model = Episode

    def __init__(self, episode_id: int, character_ids: list[int], location_id: int | None = None,
                 viewpoint_character_id: int | None = None):
        self.episode_id = episode_id
        self.character_ids = character_ids
        self.location_id = location_id
        self.viewpoint_character_id = viewpoint_character_id

    def execute(self, s: Session) -> EpisodeRecord:
        self.check_exists(s, Location, self.location_id, "location_id")
        record = common_query.get_row(s, Episode, self.episode_id)
        approved_ids = list(self.character_ids)
        if self.viewpoint_character_id is not None:
            approved_ids.append(self.viewpoint_character_id)
        for character_id in approved_ids:
            common_query.get_row(s, Character, character_id).confirmed = ConfirmStatus.APPROVED
        if self.location_id is not None:
            record.location_id = self.location_id
        if self.viewpoint_character_id is not None:
            record.viewpoint_character_id = self.viewpoint_character_id
        s.flush()
        set_characters(s, record.id, self.character_ids)
        save_mentions(s, record.id)
        return record_of(s, EpisodeRecord, record)
