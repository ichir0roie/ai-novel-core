#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.style_preference.form import StylePreferenceCreateForm
from data_access_logic.style_preference.record import StylePreferenceRecord
from db.schema import StylePreference


class CommitStylePreference(CommitEntrypoint):
    """範囲の行が無ければ足し、あればその行の末尾に足す(範囲ごとに一行)。"""

    def __init__(self, style_preference: StylePreferenceCreateForm):
        self.style_preference = style_preference

    def execute(self, s: Session) -> StylePreferenceRecord:
        form = self.style_preference
        record = s.scalar(select(StylePreference).where(StylePreference.scope == form.scope.value))
        if record is None:
            record = StylePreference()
            form.write_to(record)
            s.add(record)
        else:
            record.text = "\n\n".join(part for part in (record.text.strip(), form.text.strip()) if part)
        self.finalize(s, record)
        return StylePreferenceRecord.model_validate(record)
