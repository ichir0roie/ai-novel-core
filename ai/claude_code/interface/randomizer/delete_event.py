#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import delete, select

from ai.claude_code.interface.randomizer._base import CommitDraft
from db.schema import Event, EventCharacter, EventIdea, EventSummary


class DeleteEvent(CommitDraft):
    model = Event

    def __init__(self, event_id: int):
        self.event_id = event_id

    def execute(self, session) -> dict:
        record = self.get_or_raise(session, int(self.event_id), "出来事")
        child = session.scalars(
            select(Event.id).where(Event.parent_event_id == record.id)).first()
        if child is not None:
            raise ValueError(f"event_id={self.event_id} には子の出来事が残っている。先にそちらを消す")

        data = {"id": record.id, "name": record.name}
        # 関連は noload なので、cascade に頼らず中間テーブルと要約を先に消す
        for model in (EventCharacter, EventIdea, EventSummary):
            session.execute(delete(model).where(model.event_id == record.id))
        session.delete(record)
        return data
