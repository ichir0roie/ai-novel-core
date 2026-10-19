#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode import steps
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.episode_session.record import TextSaved
from data_access_logic.query import common_query
from db.schema import Episode


class AppendText(CommitEntrypoint):
    """語り部が、人物役の一手を起こした文を本文の終わりに書き足す。作者の書いた所は直さない。

    空行を置くなら、文の頭に空行を書く。
    """


    def __init__(self, episode_id: int, text: str):
        self.episode_id = episode_id
        self.text = text

    def execute(self, s: Session) -> TextSaved:
        if not self.text.strip():
            raise ValueError("text が空")
        before = common_query.get_row(s, Episode, self.episode_id).main_text
        joined = f"{before.rstrip()}\n{self.text}" if before.strip() else self.text
        saved = steps.commit_episode(s, EpisodeCommitForm(id=self.episode_id, main_text=joined))
        return TextSaved(episode_id=self.episode_id, letters=saved.letters)
