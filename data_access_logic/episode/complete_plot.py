#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.claude_code import ai_client
from ai.claude_code.ai_client import PLOT_EFFORT, PLOT_MODEL
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import SessionEntrypoint, record_of
from data_access_logic.episode import framer, plot_completer
from data_access_logic.episode.form import EpisodeForm, save_frame
from data_access_logic.episode.record import EpisodeRecord


class CompletePlot(SessionEntrypoint):
    """プロット補完。作者の下書き(GUI の欄の値。`story_id` 以外は空でもよい)のプロット(`plot_text`)を核に、本文全体を場面に割った
    プロット(`## 場面` / `## 狙い`)を AI に書き直させ、それでプロットをそっくり置き換える(今のプロットの中身は書き直したプロットに含めさせる)。
    本文は書かない(作者がプロット・登場人物・場所を確かめてから `GenerateEpisode` で書く)。`id` を渡せばその枠(本文の無い話)を補完する。

    書き直したプロットに出るのに登場人物にいない人物は作って(承認済みで)登場人物に足し、話の場所より細かい舞台が要れば、
    その場所の下に作って話の場所にする。
    下書きは AI 呼び出しの前に枠として一度保存する。プロットか時刻(`start`)が枠に無ければ、先に `GenerateFrame` と同じ生成で枠を決める。
    登場人物は下書きの `character_ids`、省けば枠の `episode_character`。空なら止まる。
    `order` は作者の注文(展開・焦点・雰囲気など、今のプロットに加えて新しいプロットに望むこと)。今のプロットと合わせて取り入れる。
    `model` / `effort` はプロットの書き直しと候補の呼び出しにだけ効く(省けば `PLOT_MODEL` / `PLOT_EFFORT`)。
    """

    def __init__(
        self, episode: EpisodeForm, order: str | None = None, model: str | None = None, effort: str | None = None,
        ai: AIClient = ai_client,
    ):
        self.episode = episode
        self.order = order
        self.model = model
        self.effort = effort
        self.ai = ai

    def execute(self, s: Session) -> EpisodeRecord:
        record = save_frame(s, self.episode)
        s.commit()
        if not record.plot_text.strip() or record.start is None:
            framer.frame_episode(s, self.ai, record.id)
        completed = plot_completer.complete_plot(
            s, self.ai, record.id, self.order or None, model=self.model or PLOT_MODEL, effort=self.effort or PLOT_EFFORT)
        return record_of(s, EpisodeRecord, completed)
