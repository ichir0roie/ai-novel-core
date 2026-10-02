#!/usr/bin/env python3
"""タイムライン画面(`/timeline`)の元データ。ある期間に掛かる話と出来事。"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import loading
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.event.record import EventRecord
from data_access_logic.query import common_query
from db.schema import Base, Episode, Event
from db.stamp import Stamp
from gui.api.models import TimelineBlock, TimelineResponse
from gui.api.records import reference_labels, summary_of
from gui.api.tables import spec_of

# 一度に出す話・出来事それぞれの上限(期間を広く取ると際限なく増えうるため)
TIMELINE_LIMIT = 500


def _block(s: Session, table: str, rows: Sequence[Base]) -> TimelineBlock:
    spec = spec_of(table)
    summaries = [summary_of(spec, row) for row in rows]
    return TimelineBlock(items=[summary.model_dump(mode="json") for summary in summaries],
                         labels=reference_labels(s, spec, [summary.record for summary in summaries]))


def timeline(s: Session, since: Stamp, until: Stamp, story_id: int | None, location_id: int | None) -> TimelineResponse:
    """`since`〜`until` に掛かる話(start〜end。end が空なら start の一点)と出来事(time、または start〜end)。
    `story_id` は話だけを、`location_id` はその場所と下位の場所で話・出来事の両方を絞る。時刻の無い話は置けないので出さない。"""
    location_ids = common_query.descendant_location_ids(s, location_id) if location_id is not None else None

    episode_conditions = [Episode.start.is_not(None), Episode.start <= until,
                          or_(Episode.end >= since, and_(Episode.end.is_(None), Episode.start >= since))]
    if story_id is not None:
        episode_conditions.append(Episode.story_id == story_id)
    if location_ids is not None:
        episode_conditions.append(Episode.location_id.in_(location_ids))
    episodes = s.scalars(loading(select(Episode).where(*episode_conditions)
                                 .order_by(Episode.start, Episode.id).limit(TIMELINE_LIMIT), EpisodeRecord)).all()

    event_conditions = [or_(Event.time.between(since, until),
                            and_(Event.start <= until, Event.end >= since))]
    if location_ids is not None:
        event_conditions.append(Event.location_id.in_(location_ids))
    events = s.scalars(loading(select(Event).where(*event_conditions)
                               .order_by(Event.time, Event.id).limit(TIMELINE_LIMIT), EventRecord)).all()

    return TimelineResponse(episode=_block(s, "episode", episodes), event=_block(s, "event", events),
                            limit=TIMELINE_LIMIT)
