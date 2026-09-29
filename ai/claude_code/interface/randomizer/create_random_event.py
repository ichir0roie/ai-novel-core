#!/usr/bin/env python3
"""下書きは時刻が空なので、決めてから `EventCreateForm` に読み込んで `CommitEvent` に渡す。"""
from __future__ import annotations

from ai.claude_code.interface.randomizer._base import RandomDraft
from data_access_logic.event.form import EventForm
from randomizer.random_event_generator import build_event


class CreateRandomEvent(RandomDraft):
    builder = staticmethod(build_event)
    draft_model = EventForm
