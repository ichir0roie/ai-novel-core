#!/usr/bin/env python3
"""下書きは時刻が空なので、決めてから `EventCreateForm` に読み込んで `CommitEvent` に渡す。"""
from __future__ import annotations

from data_access_logic.entrypoint import RandomDraft
from randomizer.random_event_generator import build_event


class CreateRandomEvent(RandomDraft):
    builder = staticmethod(build_event)
