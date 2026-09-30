#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.claude_code import ai_client
from ai.claude_code.ai_client import EPISODE_EFFORT, EPISODE_MODEL, PLOT_EFFORT, PLOT_MODEL
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import SessionEntrypoint, record_of
from data_access_logic.episode import caster, framer, writer
from data_access_logic.episode import summary as episode_summary
from data_access_logic.episode.form import EpisodeForm, save_frame
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.style_preference.extras import read_style_extras
from data_access_logic.style_preference.form import StyleTarget


class GenerateEpisode(SessionEntrypoint):
    """作者の下書き(GUI の欄の値。`story_id` 以外は空でもよい)から、話を一話ぶん(枠と本文)AI に書かせて足す。
    `id` を渡せばその枠(本文の無い話)へ本文を書く。

    AI 呼び出し(数分〜十数分かかることがある)の前に、下書きを枠として一度保存する。途中で失敗しても、枠は db に残る。
    プロット(`plot_text`)か時刻(`start`)が枠に無ければ、先に `GenerateFrame` と同じ生成で枠を決めてから本文を書く。
    登場人物は下書きの `character_ids`、省けば枠の `episode_character`。本文を書く前に、プロットで台詞・行動のある人物を
    AI に挙げさせて登場人物に足す(外さない)。db にいない人物は作って足す(`caster.py`)。それでも空なら止まる。
    `model` / `effort` は本文を書く呼び出しにだけ効く(省けば opus 5.5 の high)。
    `shared_style_extra` / `style_extra` は世界ごとの文体の好み。省けば db の `style_preference` から読む。
    """

    def __init__(
        self,
        episode: EpisodeForm,
        shared_style_extra: str | None = None,
        style_extra: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        ai: AIClient = ai_client
    ):
        self.episode = episode
        self.model = model
        self.effort = effort
        self.shared_style_extra = shared_style_extra
        self.style_extra = style_extra
        self.ai = ai

    def execute(self, s: Session) -> EpisodeRecord:
        record = save_frame(s, self.episode)
        s.commit()
        if not record.plot_text.strip() or record.start is None:
            framer.frame_episode(s, self.ai, record.id)
        caster.cast_from_plot(s, self.ai, record.id, model=PLOT_MODEL, effort=PLOT_EFFORT)
        extras = read_style_extras(s, StyleTarget.EPISODE).overridden(self.shared_style_extra, self.style_extra)
        written = writer.write_episode(
            s, self.ai, record.id, model=self.model or EPISODE_MODEL, effort=self.effort or EPISODE_EFFORT,
            shared_style_extra=extras.shared, style_extra=extras.own)
        if written is None:
            raise ValueError("本文が得られなかった")
        # 書いた本文から概要を作り直す(本文が変わっていなければそのまま)
        episode_summary.summarize(s, self.ai, written)
        return record_of(s, EpisodeRecord, written)
