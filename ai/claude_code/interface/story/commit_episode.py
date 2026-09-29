#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import selectinload

from ai.claude_code.interface._base import reloaded
from ai.claude_code.interface.randomizer._base import CommitAndRefresh
from ai.instructions.style import layout_novel_text
from data_access_logic.episode.form import EpisodeCommitForm, set_characters
from data_access_logic.episode.record import EpisodeRecord
from db.schema import Character, Episode, Location, Story


class CommitEpisode(CommitAndRefresh):
    model = Episode

    def __init__(self, episode: EpisodeCommitForm):
        self.episode = episode

    def execute(self, session) -> EpisodeRecord:
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
            record = self.get_or_raise(session, form.id, "話")
        for key, value in form.changed_column_values(Episode).items():
            setattr(record, key, value)
        # 手で直した話は、世界観へ戻し直すまで同期していない扱いにする
        record.synced = False
        if form.text is not None:
            record.text = layout_novel_text(form.text)
        self.finalize(session, record)
        # 渡されなければ既存の登場人物はそのまま
        if form.character_ids is not None:
            set_characters(session, record.id, form.character_ids)
        return EpisodeRecord.model_validate(reloaded(session, record, selectinload(Episode.episode_characters)))
