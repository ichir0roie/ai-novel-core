#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.style_preference.form import StylePreferenceCreateForm
from data_access_logic.style_preference.record import StylePreferenceRecord
from db.schema import StylePreference


class CommitStylePreference(CommitEntrypoint):
    model = StylePreference

    def __init__(self, style_preference: StylePreferenceCreateForm):
        self.style_preference = style_preference

    def execute(self, s: Session) -> StylePreferenceRecord:
        target = self.style_preference.target
        if s.scalar(select(StylePreference.id).where(StylePreference.target == target)) is not None:
            raise ValueError(f"target={target} の文体の好みはもうある。直すときは UpdateStylePreference を使う")
        record = StylePreference()
        self.style_preference.write_to(record)
        s.add(record)
        self.finalize(s, record)
        return StylePreferenceRecord.model_validate(record)
