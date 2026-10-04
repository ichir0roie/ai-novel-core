#!/usr/bin/env python3
"""タイムライン画面(`/timeline`)の元データ。全期間の話。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import loading
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.query import common_query
from db.schema import Episode
from gui.api.models import TimelineResponse
from gui.api.records import reference_labels, summary_of
from gui.api.tables import spec_of


def timeline(s: Session, story_id: int | None) -> TimelineResponse:
    """時刻を持つ全部の話(start〜end。end が空なら start の一点)。
    画面が全期間を一つの横に長い軸に並べ、スクロールで見て回るので期間では絞らない。
    `story_id` はその作品と子孫の作品(章・外伝)で絞る。時刻の無い話は置けないので出さない。
    押した話のモーダルを引き直さずに出せるよう、プロットは全文を添える。"""
    conditions = [Episode.start.is_not(None)]
    if story_id is not None:
        conditions.append(Episode.story_id.in_(common_query.descendant_story_ids(s, story_id)))
    episodes = s.scalars(loading(select(Episode).where(*conditions).order_by(Episode.start, Episode.id), EpisodeRecord)).all()

    spec = spec_of("episode")
    summaries = [summary_of(spec, row) for row in episodes]
    return TimelineResponse(items=[{**summary.model_dump(mode="json"), "plot_text": row.plot_text}
                                   for summary, row in zip(summaries, episodes, strict=True)],
                            labels=reference_labels(s, spec, [summary.record for summary in summaries]))
