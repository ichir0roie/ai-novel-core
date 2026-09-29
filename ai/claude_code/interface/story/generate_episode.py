#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import selectinload

from ai.claude_code import ai_client
from ai.claude_code.claude_code_time_keeper import _writer_options
from ai.claude_code.interface._base import reloaded
from ai.claude_code.interface.story._base import StoryQuery
from data_access_logic.episode import framer, writer
from data_access_logic.episode.form import EpisodeForm, save_frame
from data_access_logic.episode.record import EpisodeRecord
from db.schema import Episode


class GenerateEpisode(StoryQuery):
    """作者の下書き(GUI の欄の値。`story_id` 以外は空でもよい)から、話を一話ぶん(枠と本文)AI に書かせて足す。
    `id` を渡せばその枠(本文の無い話)へ本文を書く。

    AI 呼び出し(数分〜十数分かかることがある)の前に、下書きを枠として一度保存する。途中で失敗しても、枠は db に残る。
    種(`key`)か時刻(`start`)が枠に無ければ、先に `GenerateFrame` と同じ生成で枠を決めてから本文を書く。
    登場人物は `character_ids`(GUI の生成パネルで選んだ人物)、省けば下書きの `character_ids`、それも無ければ枠の
    `episode_character`。空なら止まる(時刻・場所から人物を拾う既定は持たない)。
    `model` / `effort` は本文を書く呼び出しにだけ効く(省けば fable の high)。
    `shared_style_extra` / `style_extra` は世界ごとの文体の好み(世界リポジトリの `instructions/style.py`)。
    """

    def __init__(self, episode: EpisodeForm, character_ids: list[int] | None = None,
                 model: str | None = None, effort: str | None = None,
                 shared_style_extra: str = "", style_extra: str = "", ai=ai_client):
        self.episode = episode
        self.character_ids = character_ids
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

    def execute(self, session) -> EpisodeRecord:
        form = self.episode.model_copy()
        if self.character_ids is not None:
            form.character_ids = self.character_ids
        record = save_frame(session, form)
        if not record.key.strip() or record.start is None:
            framer.frame_episode(session, self.ai, record.id)
        written = writer.write_episode(
            session, self.ai, record.id, writer_options=self._writer_options(),
            shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
        if written is None:
            raise ValueError("本文が得られなかった")
        return EpisodeRecord.model_validate(reloaded(session, written, selectinload(Episode.episode_characters)))
