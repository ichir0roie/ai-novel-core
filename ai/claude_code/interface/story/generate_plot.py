#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery
from ai.time_keeper import episode_generator, plot_generator


class GeneratePlot(StoryQuery):
    """作者の下書き(GUI の欄の値。`story_id` 以外は空でもよい)を核に、本文の無い話の枠(題・種・時刻・視点・場所)を
    AI に決めさせて足す。`id` を渡せばその枠(本文の無い話)を決め直す。本文は `GenerateEpisode` で別に書く。

    `character_ids` はこの話に出したい人物(省けば作品と直前の話だけを材料にする)。
    `previous_plot_ids` は直前の話(省けば作品の中でその時刻より前の三話)。
    """

    def __init__(self, plot: dict, character_ids: list[int] | None = None,
                 previous_plot_ids: list[int] | None = None, ai=ai_client):
        self.plot = dict(plot or {})
        self.character_ids = character_ids
        self.previous_plot_ids = previous_plot_ids
        self.ai = ai

    def execute(self, session) -> dict:
        draft = dict(self.plot)
        plot_id = draft.pop("id", None)
        story_id = draft.get("story_id")
        if plot_id is not None and story_id in (None, ""):
            story_id = episode_generator.frame(session, plot_id).story_id
        if story_id in (None, ""):
            raise ValueError("story_id は必須")
        record = plot_generator.generate_frame(
            session, self.ai, int(story_id), draft, self.character_ids, self.previous_plot_ids, plot_id=plot_id)
        return _rows.plot_row(record)
