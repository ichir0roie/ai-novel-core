#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.location.record import DeletedLocation
from data_access_logic.query import common_query
from db.schema import CharacterHistoryKnower, CharacterKnower, IdeaHistoryKnower, Location


class DeleteLocation(CommitEntrypoint):

    def __init__(self, location_id: int):
        self.location_id = location_id

    def execute(self, s: Session) -> DeletedLocation:
        record = common_query.get_row(s, Location, self.location_id)
        child = s.scalars(
            select(Location.id).where(Location.parent_id == record.id)).first()
        if child is not None:
            raise ValueError(f"location_id={self.location_id} には子の場所が残っている。先にそちらを消す")

        deleted = DeletedLocation.model_validate(record)
        # この場所が知る相手になっている行(住む人物が知っていたこと)も消す
        for knower_model in (CharacterKnower, CharacterHistoryKnower, IdeaHistoryKnower):
            s.execute(delete(knower_model).where(knower_model.location_id == record.id))
        s.delete(record)
        return deleted
