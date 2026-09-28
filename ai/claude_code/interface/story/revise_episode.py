#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from ai.claude_code.claude_code_time_keeper import _writer_options
from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery
from ai.time_keeper import episode_reviser


class ReviseEpisode(StoryQuery):
    """すでに本文のある話(`episode` の `id`)を、直す指示(`instruction`)に沿って AI に書き直させる。

    筋は変えず、指示にある観点だけを直す。`character_ids` はこの話に出る人物(初登場・既出とも)。
    前の話の概要に出ていない人物は、その材料から AI が初登場と判断して外見・性格の描写を厚くする。
    `model` / `effort` は本文を書く呼び出しにだけ効く(省けば fable の high)。
    `shared_style_extra` / `style_extra` は世界ごとの文体の好み(世界リポジトリの `instructions/style.py`)。
    """

    def __init__(self, episode: dict, character_ids: list[int], instruction: str = "",
                 previous_episode_ids: list[int] | None = None, place_id: int | None = None,
                 model: str | None = None, effort: str | None = None, *,
                 shared_style_extra: str = "", style_extra: str = "", ai=ai_client):
        self.episode = dict(episode or {})
        self.character_ids = character_ids
        self.instruction = instruction
        self.previous_episode_ids = previous_episode_ids
        self.place_id = place_id
        self.model = model
        self.effort = effort
        self.shared_style_extra = shared_style_extra
        self.style_extra = style_extra
        self.ai = ai

    def _writer_options(self) -> dict | None:
        if self.ai is ai_client:
            return _writer_options(self.model, self.effort)
        options = {key: value for key, value in (("model", self.model), ("effort", self.effort)) if value}
        return options or None

    def execute(self, session) -> dict:
        episode_id = self.episode.get("id")
        if episode_id is None:
            raise ValueError("episode.id は必須")
        if not self.character_ids:
            raise ValueError("character_ids(登場人物)が空")
        record = episode_reviser.generate(
            session, self.ai, int(episode_id), self.character_ids, self.instruction, self.previous_episode_ids,
            place_id=self.place_id, writer_options=self._writer_options(),
            shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
        if record is None:
            raise ValueError("本文が得られなかった")
        return _rows.episode_row(record)
