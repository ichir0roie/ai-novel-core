#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.event import steps
from data_access_logic.event.form import EventUpdateForm
from data_access_logic.event.record import EventRecord


class UpdateEvents(CommitEntrypoint):
    """出来事をまとめて直す。GUI の出来事のタイムラインの変更モードで溜めた時刻・親の移しを、一つのトランザクションで書く。
    一件ずつは GUI の修正(`UpdateEvent` の `execute`)と同じに書き、AI の段(ミーム・要約)は回さない。"""

    def __init__(self, events: list[EventUpdateForm]):
        self.events = events

    def execute(self, s: Session) -> list[EventRecord]:
        return [steps.update_event(s, event) for event in self.events]
