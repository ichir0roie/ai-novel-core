#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode_session.stage import StageSerialized, stage_of


class ReadStage(SessionEntrypoint):
    """語り部が手番を回すときに読む材料。プロット・時刻・場所・登場人物の表層(名前・年齢・性別・外見)・登場人物のだれとだれが知り合いか。
    人物の芯・来歴、関係の説明・来歴、設定、前の話・本文は入らない。
    話の周りの出来事(同じ作品の前の話の時刻から次の話の時刻の手前まで)は、人物・場所を問わず本文で、話の前・あいだ・後に分けて入る。"""

    def __init__(self, episode_id: int):
        self.episode_id = episode_id

    def execute(self, s: Session) -> StageSerialized:
        return stage_of(s, self.episode_id)
