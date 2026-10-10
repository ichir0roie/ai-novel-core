#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.event.record import DeletedEvent
from data_access_logic.query import common_query
from db.schema import Event, EventCharacter, EventSummary


class DeleteEvent(CommitEntrypoint):
    """出来事を消す。`with_children` なら子孫の出来事もいっしょに消し、そうでなければ子が残っているときは止める。"""

    def __init__(self, event_id: int, with_children: bool = False):
        self.event_id = event_id
        self.with_children = with_children

    def execute(self, s: Session) -> DeletedEvent:
        record = common_query.get_row(s, Event, self.event_id)
        children = s.scalars(select(Event.id).where(Event.parent_event_id == record.id)).all()
        if children and not self.with_children:
            raise ValueError(f"event_id={self.event_id} には子の出来事が残っている。先にそちらを消す")

        deleted = DeletedEvent.model_validate(record)
        for event_id in [*_descendants(s, children), record.id]:
            # 関連は noload なので、cascade に頼らず中間テーブルと要約を先に消す
            for model in (EventCharacter, EventSummary):
                s.execute(delete(model).where(model.event_id == event_id))
            s.execute(delete(Event).where(Event.id == event_id))
        return deleted


def _descendants(s: Session, ids: list[int]) -> list[int]:
    """`ids` とその子孫を、子が親より先に来る順(消す順)に並べる。"""
    ordered: list[int] = []
    for event_id in ids:
        children = s.scalars(select(Event.id).where(Event.parent_event_id == event_id)).all()
        ordered += [*_descendants(s, list(children)), event_id]
    return ordered
