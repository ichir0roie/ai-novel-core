#!/usr/bin/env python3
from __future__ import annotations

import difflib

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode import steps
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.episode_session.record import SessionRecord, TextSaved
from data_access_logic.episode_session.turns import author_session_running, author_turn, write_author_line
from data_access_logic.query import common_query
from db.schema import Episode

# 差分に添える前後の行の数。語り部が、変わった所がどの場面かを読めるだけ
_CONTEXT_LINES = 2


def diff_text(before: str, after: str) -> str:
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(), n=_CONTEXT_LINES, lineterm="")
    # 先頭の二行(--- / +++)はファイル名の行なので落とす
    return "\n".join(list(lines)[2:])


class SaveText(CommitEntrypoint):
    """作者が画面で書いた本文を保存する。作者の番なら、前に保存した本文からの差分を作者の行に入れ、番を語り部へ返す。

    作者と語り部が本文を代わる代わる書いているあいだ(`author_session_running`)、語り部の番には保存させない
    (語り部が書き足した本文を、作者の手元の古い本文で上書きしないため)。作者の行の無いセッションでは、いつでも保存できる。
    """


    def __init__(self, episode_id: int, main_text: str):
        self.episode_id = episode_id
        self.main_text = main_text

    def execute(self, s: Session) -> TextSaved:
        before = common_query.get_row(s, Episode, self.episode_id).main_text
        waiting = author_turn(s, self.episode_id)
        if waiting is None and author_session_running(s, self.episode_id):
            raise ValueError("語り部の番なので本文を保存できない。作者の番になってから保存する")
        saved = steps.commit_episode(s, EpisodeCommitForm(id=self.episode_id, main_text=self.main_text))
        text = diff_text(before, saved.main_text)
        if waiting is None or not text:
            return TextSaved(episode_id=self.episode_id, letters=saved.letters)
        record = write_author_line(s, self.episode_id, text)
        self.finalize(s, record)
        return TextSaved(episode_id=self.episode_id, letters=saved.letters, record=record_of(s, SessionRecord, record))
