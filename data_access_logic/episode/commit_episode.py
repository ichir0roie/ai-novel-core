#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.instructions.style import layout_novel_text
from data_access_logic.ai_entrypoint import CommitAndRefresh
from data_access_logic.entrypoint import record_of
from data_access_logic.episode.form import EpisodeCommitForm, set_characters
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.query import common_query
from db.schema import Character, Episode, Location, Story


class CommitEpisode(CommitAndRefresh):
    model = Episode

    def __init__(self, episode: EpisodeCommitForm):
        self.episode = episode

    def execute(self, session: Session) -> EpisodeRecord:
        form = self.episode
        self.check_exists(session, Story, form.story_id, "story_id")
        self.check_exists(session, Character, form.viewpoint_character_id, "viewpoint_character_id")
        self.check_exists(session, Location, form.place_id, "place_id")
        for character_id in form.character_ids or []:
            self.check_exists(session, Character, character_id, "character_ids")

        if form.id is None:
            record = Episode(key="", title="")
            session.add(record)
        else:
            record = common_query.get_row(session, Episode, form.id)
        form.write_changes_to(record)
        # 手で直した話は、世界観へ戻し直すまで同期していない扱いにする(GUI で同期フラグを渡されたらそれに従う)
        if form.synced is None:
            record.synced = False
        if form.text is not None:
            record.text = layout_novel_text(form.text)
        self.finalize(session, record)
        # 渡されなければ既存の登場人物はそのまま
        if form.character_ids is not None:
            set_characters(session, record.id, form.character_ids)
        return record_of(session, EpisodeRecord, record)
