#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode import brief
from data_access_logic.episode.models import EpisodeCastingSerialized


class ReadEpisodeCasting(SessionEntrypoint):
    """話(`episode_id`)の本文の材料を読む前に、このセッションの Claude がプロットから登場人物・場所を決めるための材料を読む。

    この話(題・時刻・場所・視点・プロット)・今の登場人物・名前だけ出る人物・登場人物の候補(プロット・本文に名前が出る人物・
    登場人物と関係のある人物・話の場所にいる人物)・話の場所の中の既知の場所と、登場人物・名前だけ出る人物それぞれが関わった話
    (概要つき)を、id 付きで返す。話の時刻(`start`)が空なら止まる。
    関わった話の概要が無いか本文と食い違っていれば、読む前に AI で作り直す。
    決めた登場人物・場所は `CastEpisode` で結んでから、`ReadEpisodeBrief` で本文の材料を読む。
    """

    def __init__(self, episode_id: int, ai: AIClient = ai_client):
        self.episode_id = episode_id
        self.ai = ai

    def execute(self, s: Session) -> EpisodeCastingSerialized:
        return brief.read_casting(s, self.ai, self.episode_id)
