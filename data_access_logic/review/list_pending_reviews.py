#!/usr/bin/env python3
"""ユーザの判断が要るものを一覧にする、claude が呼ぶ入口(週次ルーチン)。db には書かない。

    ListPendingReviews().show()

候補のアイデア・候補のミーム・世界観へ反映していない話・本文に残った TODO を、
`{"key", "kind", "title", "detail"}` の形(`items.PendingReview`)で返す。`key` は同じものを二度タスクにしないための印。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.review import items


class ListPendingReviews(SessionEntrypoint):
    def execute(self, s: Session) -> list[items.PendingReview]:
        return [*items.candidate_items(s),
                *items.unconfirmed_meme_items(s),
                *items.unsynced_episode_items(s),
                *items.todo_items(s)]
