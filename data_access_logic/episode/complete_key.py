#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.claude_code import ai_client
from ai.claude_code.ai_client import KEY_EFFORT, KEY_MODEL
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import SessionEntrypoint, record_of
from data_access_logic.episode import framer, key_completer
from data_access_logic.episode.form import EpisodeForm, save_frame
from data_access_logic.episode.record import EpisodeRecord


class CompleteKey(SessionEntrypoint):
    """キー情報補完。作者の下書き(GUI の欄の値。`story_id` 以外は空でもよい)の種(`key`)を核に、本文全体を場面に割った
    種(`## 場面` / `## 狙い`)を AI に書き直させ、それで種をそっくり置き換える(今の種の中身は書き直した種に含めさせる)。
    本文は書かない(作者が種・登場人物・場所を確かめてから `GenerateEpisode` で書く)。`id` を渡せばその枠(本文の無い話)を補完する。

    書き直した種に出るのに登場人物にいない人物は作って(承認済みで)登場人物に足し、話の場所より細かい舞台が要れば、
    その場所の下に作って話の場所にする。
    下書きは AI 呼び出しの前に枠として一度保存する。種か時刻(`start`)が枠に無ければ、先に `GenerateFrame` と同じ生成で枠を決める。
    登場人物は下書きの `character_ids`、省けば枠の `episode_character`。空なら止まる。
    `order` は作者の注文(展開・焦点・雰囲気など、今の種に加えて新しい種に望むこと)。今の種と合わせて取り入れる。
    `model` / `effort` は種の書き直しと候補の呼び出しにだけ効く(省けば `KEY_MODEL` / `KEY_EFFORT`)。
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
        if not record.key.strip() or record.start is None:
            framer.frame_episode(s, self.ai, record.id)
        completed = key_completer.complete_key(
            s, self.ai, record.id, self.order or None, model=self.model or KEY_MODEL, effort=self.effort or KEY_EFFORT)
        return record_of(s, EpisodeRecord, completed)
