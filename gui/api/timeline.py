#!/usr/bin/env python3
"""タイムライン画面(`/timeline`)の元データ。全期間の話と出来事。"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import loading
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.event.record import EventRecord
from data_access_logic.query import common_query
from db.schema import Base, Episode, Event
from gui.api.models import TimelineBlock, TimelineResponse
from gui.api.records import reference_labels, summary_of
from gui.api.tables import spec_of


def _block(s: Session, table: str, rows: Sequence[Base]) -> TimelineBlock:
    spec = spec_of(table)
    summaries = [summary_of(spec, row) for row in rows]
    return TimelineBlock(items=[summary.model_dump(mode="json") for summary in summaries],
                         labels=reference_labels(s, spec, [summary.record for summary in summaries]))


def timeline(s: Session, story_id: int | None, location_id: int | None) -> TimelineResponse:
    """時刻を持つ全部の話(start〜end。end が空なら start の一点)と出来事(time、期間があれば start〜end も)。
    画面が全期間を一つの横に長い軸に並べ、スクロールで見て回るので期間では絞らない。
    `story_id` は話だけを、`location_id` はその場所と下位の場所で話・出来事の両方を絞る。時刻の無い話・出来事は置けないので出さない。"""
    location_ids = common_query.descendant_location_ids(s, location_id) if location_id is not None else None

    episode_conditions = [Episode.start.is_not(None)]
    if story_id is not None:
        episode_conditions.append(Episode.story_id == story_id)
    if location_ids is not None:
        episode_conditions.append(Episode.location_id.in_(location_ids))
    episodes = s.scalars(loading(select(Episode).where(*episode_conditions).order_by(Episode.start, Episode.id), EpisodeRecord)).all()

    event_conditions = [Event.time.is_not(None)]
    if location_ids is not None:
        event_conditions.append(Event.location_id.in_(location_ids))
    events = s.scalars(loading(select(Event).where(*event_conditions).order_by(Event.time, Event.id), EventRecord)).all()

    return TimelineResponse(episode=_block(s, "episode", episodes), event=_block(s, "event", events))
