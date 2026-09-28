#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from ai.claude_code.claude_code_time_keeper import _writer_options
from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery
from ai.time_keeper import episode_generator, episode_reviser
from db.schema import Episode


class ReviseEpisode(StoryQuery):
    """すでに本文のある話(`episode` の `id`)を、直す指示(`instruction`。必須)に沿って AI に書き直させる。

    筋は変えず、指示にある観点だけを直す。登場人物(この話に出る人物。初登場・既出とも)は下書きの `character_ids`
    (話の `episode_character` と同じ欄)。下書きに無ければこの話の `episode_character`。空なら止まる。
    前の話の概要に出ていない人物は、その材料から AI が初登場と判断して外見・性格の描写を厚くする。
    `model` / `effort` は本文を書く呼び出しにだけ効く(省けば fable の high)。
    `shared_style_extra` / `style_extra` は世界ごとの文体の好み(世界リポジトリの `instructions/style.py`)。

    `episode` に `id` 以外の欄(題・種など)があれば、AI 呼び出し(数分かかることがある)の前に
    その下書きの値を一度保存する。途中で失敗しても、この保存分は db に残る。
    """

    def __init__(self, episode: dict, instruction: str, previous_episode_ids: list[int] | None = None,
                 model: str | None = None, effort: str | None = None, *,
                 shared_style_extra: str = "", style_extra: str = "", ai=ai_client):
        self.episode = dict(episode or {})
        self.instruction = instruction
        self.previous_episode_ids = previous_episode_ids
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
        record = session.get(Episode, int(episode_id))
        if record is None:
            raise ValueError(f"話 id={episode_id} が見つからない")
        draft = {k: v for k, v in self.episode.items()
                 if k not in ("id", "text", "synced", "letters", "character_ids")}
        character_ids = episode_generator.resolve_character_ids(
            session, record.id, self.episode.get("character_ids"))
        if draft:
            # AI 呼び出し(数分かかることがある)の前に、題・種など今の下書きの値を一度保存しておく
            episode_generator.save_draft(session, record, draft)
        revised = episode_reviser.generate(
            session, self.ai, int(episode_id), character_ids, self.instruction, self.previous_episode_ids,
            writer_options=self._writer_options(),
            shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
        if revised is None:
            raise ValueError("本文が得られなかった")
        return _rows.episode_row(revised)
