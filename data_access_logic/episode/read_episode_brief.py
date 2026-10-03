#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode import brief
from data_access_logic.episode.models import EpisodeBriefSerialized


class ReadEpisodeBrief(SessionEntrypoint):
    """話(`episode_id`)の本文を、このセッションの Claude が自分で書く・直すための材料を読む。

    書き方(文体の決まりと `style_preference`)・作品・前の話・この話(プロット・今の本文)・登場人物・名前だけ出る人物・
    登場人物の関係・関係する設定(話に結んだアイデアのうち、話の時刻に効くもの)・場所・前後の出来事を、id 付きで返す。
    話の時刻(`start`)が空なら止まる。
    前の話・出来事の要約が本文と食い違っていれば、読む前に AI で作り直す(本文は書かない)。
    """

    def __init__(self, episode_id: int, ai: AIClient = ai_client):
        self.episode_id = episode_id
        self.ai = ai

    def execute(self, s: Session) -> EpisodeBriefSerialized:
        return brief.read_brief(s, self.ai, self.episode_id)
