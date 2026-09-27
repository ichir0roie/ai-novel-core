#!/usr/bin/env python3
"""ユーザの判断が要るものを一覧にする、claude が呼ぶ入口(週次ルーチン)。db には書かない。

    ListPendingReviews().run()

候補のアイデア・世界観へ反映していない話・本文に残った TODO を、
`{"key", "kind", "title", "detail"}` の辞書で返す。`key` は同じものを二度タスクにしないための印。
"""
from __future__ import annotations

from ai.claude_code.interface._base import SessionEntrypoint
from ai.claude_code.interface.review import _items


class ListPendingReviews(SessionEntrypoint):
    def execute(self, session) -> list[dict]:
        return [*_items.candidate_items(session),
                *_items.unsynced_plot_items(session),
                *_items.todo_items(session)]
