#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from ai.claude_code.interface._base import UnknownRecordError
from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryCommit
from ai.instructions.style import layout_novel_text
from ai.time_keeper import generated_content
from db.schema import Episode, Story, get_env_session


class CommitEpisode(StoryCommit):
    model = Episode

    def __init__(self, episode: str | dict):
        self.episode = episode

    def execute(self, session) -> dict:
        """手で書いた本文なので model・effort は空にする(AI が書いたときだけ値が入る)。"""
        data = self.parse(self.episode)
        episode_id = data.pop("id", None)
        data.pop("synced", None)
        data.pop("letters", None)
        text = data.pop("text", None)
        self.check_columns(data)
        record = None
        if episode_id is not None:
            record = session.get(Episode, episode_id)
            if record is None:
                raise UnknownRecordError(f"id={episode_id} という話が見つからない")
        elif data.get("story_id") in (None, ""):
            raise ValueError("story_id は必須(id を渡さず新しい話を足すとき)")

        if record is None or "key" in data or text is not None:
            key = data.get("key", "" if record is None else record.key)
            body = text if text is not None else ("" if record is None else record.text)
            if key in (None, "") and body in (None, ""):
                raise ValueError("key(種)か text(本文)のどちらかは必須")
        if "story_id" in data:
            self.check_exists(session, Story, data["story_id"], "story_id")

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
            record.model = record.effort = None
        self.finalize(session, record)
        return _rows.episode_row(record)

    def run(self) -> dict:
        result = super().run()
        with get_env_session() as session:
            generated_content.refresh(session, ai_client, session.get(Episode, result["id"]))
        return result
