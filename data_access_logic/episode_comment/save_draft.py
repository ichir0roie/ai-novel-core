#!/usr/bin/env python3
from __future__ import annotations

import difflib

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode import steps
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.episode_comment.record import CommentDiff, DraftSaved
from data_access_logic.query import common_query
from db.schema import Episode, EpisodeCommentDiff

# 差分に添える前後の行の数。反応する側が、変わった所がどの場面かを読めるだけ
_CONTEXT_LINES = 2


def diff_text(before: str, after: str) -> str:
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(), n=_CONTEXT_LINES, lineterm="")
    # 先頭の二行(--- / +++)はファイル名の行なので落とす
    return "\n".join(list(lines)[2:])


class SaveDraft(CommitEntrypoint):
    """ユーザが書いている本文を保存し、前に保存した本文から変わった箇所を差分の表に足す(語り部と人物役がそれを読んで反応する)。"""

    def __init__(self, episode_id: int, main_text: str):
        self.episode_id = episode_id
        self.main_text = main_text

    def execute(self, s: Session) -> DraftSaved:
        before = common_query.get_row(s, Episode, self.episode_id).main_text
        saved = steps.commit_episode(s, EpisodeCommitForm(id=self.episode_id, main_text=self.main_text))
        text = diff_text(before, saved.main_text)
        if not text:
            return DraftSaved(episode_id=self.episode_id, letters=saved.letters)
        diff = EpisodeCommentDiff(episode_id=self.episode_id, diff_text=text)
        s.add(diff)
        self.finalize(s, diff)
        return DraftSaved(episode_id=self.episode_id, letters=saved.letters, diff=record_of(s, CommentDiff, diff))
