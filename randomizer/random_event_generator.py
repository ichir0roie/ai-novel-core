#!/usr/bin/env python3
from __future__ import annotations

import factory

from data_access_logic.event.form import EventForm


class EventFactory(factory.Factory):
    class Meta:
        model = EventForm

    name = factory.Sequence(lambda n: f"仮の出来事{n}")
    hidden = False
    text = ""
    time = None
    parent_event_id = None
    location_id = None
    # class 属性の [] を使い回さないよう、ビルドごとに新しいリストを作る
    character_ids = factory.LazyFunction(list)
    start = None
    end = None


def build_event(**overrides) -> EventForm:
    return EventFactory.build(**overrides)
