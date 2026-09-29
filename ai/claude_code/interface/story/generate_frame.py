#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import selectinload

from ai.claude_code import ai_client
from ai.claude_code.interface._base import reloaded
from ai.claude_code.interface.story._base import StoryQuery
from data_access_logic.episode import framer
from data_access_logic.episode.form import EpisodeForm, save_frame
from data_access_logic.episode.record import EpisodeRecord
from db.schema import Episode


class GenerateFrame(StoryQuery):
    """作者の下書き(GUI の欄の値。`story_id` 以外は空でもよい)を核に、本文の無い話の枠(題・種・時刻)を
    AI に決めさせて足す。`id` を渡せばその枠(本文の無い話)を決め直す。本文は `GenerateEpisode` で別に書く。

    下書きは AI 呼び出しの前に枠として一度保存する。視点・場所は AI に決めさせず、下書きの値のまま残す。
    登場人物は `character_ids`(GUI の生成パネルで選んだ人物)、省けば下書きの `character_ids` で、枠の
    `episode_character` として残す。どちらも無ければ枠の `episode_character`(空なら作品と直前の話だけを材料にする)。
    """

    def __init__(self, frame: EpisodeForm, character_ids: list[int] | None = None, ai=ai_client):
        self.frame = frame
        self.character_ids = character_ids
        self.ai = ai

    def execute(self, session) -> EpisodeRecord:
        form = self.frame.model_copy()
        if self.character_ids is not None:
            form.character_ids = self.character_ids
        record = save_frame(session, form)
        framed = framer.frame_episode(session, self.ai, record.id)
        return EpisodeRecord.model_validate(reloaded(session, framed, selectinload(Episode.episode_characters)))
