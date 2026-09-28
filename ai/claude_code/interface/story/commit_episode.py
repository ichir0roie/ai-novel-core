#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import delete, select

from ai.claude_code.interface.randomizer._base import CommitAndRefresh
from ai.claude_code.interface.story import _rows
from ai.instructions.style import layout_novel_text
from db.schema import Character, Episode, EpisodeCharacter, Location, Story


class CommitEpisode(CommitAndRefresh):
    model = Episode

    def __init__(self, episode: str | dict):
        self.episode = episode

    def execute(self, session) -> dict:
        data = self.parse(self.episode)
        episode_id = data.pop("id", None)
        data.pop("synced", None)
        data.pop("letters", None)
        text = data.pop("text", None)
        character_ids = data.pop("character_ids", None)
        if character_ids is not None:
            character_ids = [int(id_) for id_ in character_ids]
        self.check_columns(data)
        record = None
        if episode_id is not None:
            record = self.get_or_raise(session, episode_id, "話")
        elif data.get("story_id") in (None, ""):
            raise ValueError("story_id は必須(id を渡さず新しい話を足すとき)")

        if "story_id" in data:
            self.check_exists(session, Story, data["story_id"], "story_id")
        if "viewpoint_character_id" in data:
            self.check_exists(session, Character, data["viewpoint_character_id"], "viewpoint_character_id")
        if "place_id" in data:
            self.check_exists(session, Location, data["place_id"], "place_id")
        for character_id in character_ids or []:
            self.check_exists(session, Character, character_id, "character_ids")

        if record is None:
            data.setdefault("key", "")
            data.setdefault("title", "")
            record = Episode(**data)
            session.add(record)
        else:
            for key, value in data.items():
                setattr(record, key, value)
        record.synced = False
        if text is not None:
            record.text = layout_novel_text(str(text or ""))
        self.finalize(session, record)
        # `episode_characters` は noload なので、中間テーブルを直接置き換える
        # (渡されなければ既存の関連はそのまま)
        if character_ids is not None:
            session.execute(delete(EpisodeCharacter).where(EpisodeCharacter.episode_id == record.id))
            session.add_all([EpisodeCharacter(episode_id=record.id, character_id=character_id)
                             for character_id in character_ids])
            session.flush()
        current_character_ids = character_ids if character_ids is not None else list(session.scalars(
            select(EpisodeCharacter.character_id)
            .where(EpisodeCharacter.episode_id == record.id).order_by(EpisodeCharacter.id)))
        return {**_rows.episode_row(record), "character_ids": current_character_ids}
