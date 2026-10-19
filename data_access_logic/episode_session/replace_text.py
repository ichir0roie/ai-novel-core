#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode import steps
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.episode_session.record import TextSaved
from data_access_logic.query import common_query
from db.schema import Episode


class ReplaceText(CommitEntrypoint):
    """語り部が、本文のうち `old` の箇所を `new` に置き換える(作者がプロットのように書いた所を、本文の文に起こし直す)。

    `old` は本文にちょうど一度だけ出る文にする(どこを置き換えるかを取り違えないため)。
    """


    def __init__(self, episode_id: int, old: str, new: str):
        self.episode_id = episode_id
        self.old = old
        self.new = new

    def execute(self, s: Session) -> TextSaved:
        if not self.old.strip():
            raise ValueError("old が空")
        before = common_query.get_row(s, Episode, self.episode_id).main_text
        found = before.count(self.old)
        if found != 1:
            raise ValueError(f"old が本文に {found} 度出る。ちょうど一度だけ出る文にする")
        saved = steps.commit_episode(s, EpisodeCommitForm(id=self.episode_id, main_text=before.replace(self.old, self.new)))
        return TextSaved(episode_id=self.episode_id, letters=saved.letters)
