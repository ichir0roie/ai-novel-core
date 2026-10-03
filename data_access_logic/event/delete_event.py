#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.event.record import DeletedEvent
from data_access_logic.query import common_query
from db.schema import Event, EventCharacter, EventSummary


class DeleteEvent(CommitEntrypoint):
    model = Event

    def __init__(self, event_id: int):
        self.event_id = event_id

    def execute(self, s: Session) -> DeletedEvent:
        record = common_query.get_row(s, Event, self.event_id)
        child = s.scalars(
            select(Event.id).where(Event.parent_event_id == record.id)).first()
        if child is not None:
            raise ValueError(f"event_id={self.event_id} には子の出来事が残っている。先にそちらを消す")

        deleted = DeletedEvent.model_validate(record)
        # 関連は noload なので、cascade に頼らず中間テーブルと要約を先に消す
        for model in (EventCharacter, EventSummary):
            s.execute(delete(model).where(model.event_id == record.id))
        s.delete(record)
        return deleted
