#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.style_preference.form import StylePreferenceCreateForm
from data_access_logic.style_preference.record import StylePreferenceRecord
from db.schema import StylePreference


class CommitStylePreference(CommitEntrypoint):

    def __init__(self, style_preference: StylePreferenceCreateForm):
        self.style_preference = style_preference

    def execute(self, s: Session) -> StylePreferenceRecord:
        record = StylePreference()
        self.style_preference.write_to(record)
        s.add(record)
        self.finalize(s, record)
        return StylePreferenceRecord.model_validate(record)
