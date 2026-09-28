#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery
from ai.time_keeper import episode_generator, frame_generator


class GenerateFrame(StoryQuery):
    """作者の下書き(GUI の欄の値。`story_id` 以外は空でもよい)を核に、本文の無い話の枠(題・種・時刻・視点・場所)を
    AI に決めさせて足す。`id` を渡せばその枠(本文の無い話)を決め直す。本文は `GenerateEpisode` で別に書く。

    登場人物は `character_ids`(GUI の生成パネルで選んだ人物)、省けば下書きの `character_ids`(話の `episode_character`
    と同じ欄)で、足した枠の `episode_character` にも残す。どちらも無ければ枠の `episode_character`、
    枠も無ければ作品と直前の話だけを材料にする。
    `previous_episode_ids` は直前の話(省けば作品の中でその時刻より前の三話)。
    """

    def __init__(self, frame: dict, character_ids: list[int] | None = None,
                 previous_episode_ids: list[int] | None = None, ai=ai_client):
        self.frame = dict(frame or {})
        self.character_ids = character_ids
        self.previous_episode_ids = previous_episode_ids
        self.ai = ai

    def execute(self, session) -> dict:
        draft = dict(self.frame)
        episode_id = draft.pop("id", None)
        character_ids = draft.pop("character_ids", None)
        if self.character_ids is not None:
            character_ids = self.character_ids
        story_id = draft.get("story_id")
        if episode_id is not None and story_id in (None, ""):
            story_id = episode_generator.frame(session, episode_id).story_id
        if story_id in (None, ""):
            raise ValueError("story_id は必須")
        record = frame_generator.generate_frame(
            session, self.ai, int(story_id), draft, character_ids, self.previous_episode_ids,
            episode_id=episode_id)
        return _rows.episode_row(record)
