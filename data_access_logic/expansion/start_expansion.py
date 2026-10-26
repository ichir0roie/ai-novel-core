#!/usr/bin/env python3
"""世界の展開を一回始める(`.docs/world-expansion.md`)。返った id を書き手と一緒に立てて(`db.writer.writing`)、
その中で書いた行を `expansion_change` に記録する。

    StartExpansion(ExpansionCreateForm(mode="author", prompt="北の港で疫病が流行る", story_id=3)).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.expansion.form import ExpansionCreateForm
from data_access_logic.expansion.record import ExpansionRecord
from db.schema import Character, Expansion, Location, Story


def start(s: Session, form: ExpansionCreateForm) -> ExpansionRecord:
    CommitEntrypoint.check_exists(s, Story, form.story_id, "story_id")
    CommitEntrypoint.check_exists(s, Character, form.actor_id, "actor_id")
    CommitEntrypoint.check_exists(s, Location, form.location_id, "location_id")
    record = Expansion()
    form.write_to(record)
    s.add(record)
    CommitEntrypoint.finalize(s, record)
    return ExpansionRecord.model_validate(record)


class StartExpansion(CommitEntrypoint):
    def __init__(self, expansion: ExpansionCreateForm):
        self.expansion = expansion

    def execute(self, s: Session) -> ExpansionRecord:
        return start(s, self.expansion)
