#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel

from ai.claude_code.interface._base import SessionEntrypoint


class WorldQuery(SessionEntrypoint):
    def execute(self, session) -> list[BaseModel]:
        rows = session.scalars(self.select()).all()
        return [self.row(row) for row in rows]

    def select(self):
        raise NotImplementedError

    def row(self, row) -> BaseModel:
        raise NotImplementedError
