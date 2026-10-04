#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import Entrypoint
from data_access_logic.episode.form import EpisodeForm
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.flows import episode


class GenerateFrame(Entrypoint):
    """作者の下書き(GUI の欄の値。`story_id` 以外は空でもよい)を核に、本文の無い話の枠(題・プロット・時刻)を
    AI に決めさせて足す。`id` を渡せばその枠(本文の無い話)を決め直す。本文はスキル `episode` で Claude が書く。

    下書きは AI 呼び出しの前に枠として一度保存する。視点・場所は AI に決めさせず、下書きの値のまま残す。
    登場人物は下書きの `character_ids` で、枠の `episode_character` として残す。省けば枠の `episode_character`
    (空なら作品と直前の話だけを材料にする)。
    下書き・決めたプロットに名前が出るだけの人物は `episode_character` の `mentioned` の行にし、その設定を AI に渡す。
    """

    def __init__(self, frame: EpisodeForm, ai: AIClient = ai_client):
        self.frame = frame
        self.ai = ai

    def result(self) -> EpisodeRecord:
        return episode.generate_frame(self.frame, self.ai)
