#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.episode.form import EpisodeForm
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.flows import episode


class CompletePlot(Entrypoint):
    """プロット補完。作者の下書き(GUI の欄の値。`story_id` 以外は空でもよい)のプロット(`plot_text`)を核に、本文全体を場面に割った
    プロット(`## 場面` / `## 狙い`)を AI に書き直させ、それでプロットをそっくり置き換える(今のプロットの中身は書き直したプロットに含めさせる)。
    本文は書かない(作者がプロット・登場人物・場所を確かめてから、スキル `episode` で Claude が書く)。`id` を渡せばその枠(本文の無い話)を補完する。

    書き直したプロットに出るのに登場人物にいない人物は作って登場人物に足し、話の場所より細かい舞台が要れば、
    その場所の下に作って話の場所にする。書き直したプロットに名前が出る既存の人物は作らず、`episode_character` の
    `mentioned` の行にする(登場人物にするかは作者が決める)。
    下書きは AI 呼び出しの前に枠として一度保存する。プロットか時刻(`start`)が枠に無ければ、先に `GenerateFrame` と同じ生成で枠を決める。
    登場人物は下書きの `character_ids`、省けば枠の `episode_character`。空なら止まる。
    `order` は作者の注文(展開・焦点・雰囲気など、今のプロットに加えて新しいプロットに望むこと)。今のプロットと合わせて取り入れる。
    `model` / `effort` はプロットの書き直しと候補の呼び出しにだけ効く(省けば AI の client の既定の `MODEL` / `EFFORT`)。
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

    def result(self) -> EpisodeRecord:
        return episode.complete_plot(self.episode, self.order, self.model, self.effort, self.ai)
