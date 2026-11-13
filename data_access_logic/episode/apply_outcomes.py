#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode import outcomes
from data_access_logic.episode.outcomes import AppliedOutcomes, CharacterOutcome, OutcomesForm, SessionSpeech


class ApplyOutcomes(CommitEntrypoint):
    """本文を確定した話に、登場人物ごとの差分とセリフを AI を挟まずに入れる(`data_access_logic/episode/outcomes.py`)。
    手番を回した話で、`tool.episode_session apply` が人物役の差分と手番のセリフを集めて呼ぶ。"""

    def __init__(self, episode_id: int, outcomes: list[CharacterOutcome], speeches: list[SessionSpeech] | None = None):
        self.form = OutcomesForm(episode_id=episode_id, outcomes=outcomes, speeches=speeches)

    def execute(self, s: Session) -> AppliedOutcomes:
        return outcomes.apply_outcomes(s, self.form)
