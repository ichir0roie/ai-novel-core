#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from data_access_logic.style_preference.form import StylePreferenceUpdateForm
from data_access_logic.style_preference.record import StylePreferenceRecord
from db.schema import StylePreference


class UpdateStylePreference(CommitEntrypoint):

    def __init__(self, style_preference: StylePreferenceUpdateForm):
        self.style_preference = style_preference

    def execute(self, s: Session) -> StylePreferenceRecord:
        record = common_query.get_row(s, StylePreference, self.style_preference.id)
        scope = self.style_preference.scope
        if scope is not None and scope.value != record.scope and s.scalar(
                select(StylePreference.id).where(StylePreference.scope == scope.value)) is not None:
            raise ValueError(f"範囲が{scope.value}の行は既にある(範囲ごとに一行)")
        self.style_preference.write_changes_to(record)
        self.finalize(s, record)
        return StylePreferenceRecord.model_validate(record)
