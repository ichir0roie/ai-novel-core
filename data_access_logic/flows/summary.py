#!/usr/bin/env python3
"""材料に要約で渡す出来事・話の要約を、本文へ揃える流れ。

AI の結果は得たその場で一件ずつ書き戻す(後の要約で AI が落ちても、それまでの要約は残す)。
"""
from __future__ import annotations

import logging

from data_access_logic.ai_client import AIClient
from data_access_logic.episode import steps as episode_steps
from data_access_logic.episode.summary import summary_draft as episode_summary_draft
from data_access_logic.event import steps as event_steps
from data_access_logic.event.summary import summary_draft as event_summary_draft
from data_access_logic.story import steps as story_steps
from data_access_logic.story.steps import ScopeForm
from data_access_logic.summary_targets import SummaryTargets
from data_access_logic.caller import call
from db import story_scope

logger = logging.getLogger(__name__)


def rewrite_event_summaries(ai: AIClient, event_ids: list[int] | None) -> int:
    """`event_ids` を省けばすべての出来事。要約が本文と食い違っている出来事だけを作り直し、作り直した件数を返す。"""
    written = 0
    for source in call(event_steps.stale_summary_sources, event_steps.SummaryScope(event_ids=event_ids)):
        # 出来事の時刻は、その出来事の暦で AI に見せる(暦をまたいで一度に作り直すことがあるので)
        scope = call(story_steps.read_scope, ScopeForm(args={"event_id": source.id})).scope()
        with story_scope.scoped(scope):
            draft = event_summary_draft(ai, source)
        if draft is None:
            logger.warning(f"出来事 id={source.id} の要約を作れなかった(AI が答えなかった)")
            continue
        call(event_steps.write_summary,
             event_steps.SummaryForm(event_id=source.id, source_hash=source.source_hash, text=draft.text))
        written += 1
    return written


def rewrite_episode_summaries(ai: AIClient, episode_ids: list[int] | None) -> int:
    """`episode_ids` を省けばすべての話。要約が本文と食い違っている話だけを作り直し、作り直した件数を返す。"""
    written = 0
    for source in call(episode_steps.stale_summary_sources, episode_steps.EpisodeSummaryScope(episode_ids=episode_ids)):
        scope = call(story_steps.read_scope, ScopeForm(args={"episode_id": source.id})).scope()
        with story_scope.scoped(scope):
            draft = episode_summary_draft(ai, source)
        if draft is None:
            logger.warning(f"話 id={source.id} の要約を作れなかった(AI が答えなかった)")
            continue
        call(episode_steps.write_summary,
             episode_steps.EpisodeSummaryForm(episode_id=source.id, source_hash=source.source_hash, text=draft.text))
        written += 1
    return written


def refresh(ai: AIClient, targets: SummaryTargets) -> None:
    if targets.event_ids:
        rewrite_event_summaries(ai, list(dict.fromkeys(targets.event_ids)))
    if targets.episode_ids:
        rewrite_episode_summaries(ai, list(dict.fromkeys(targets.episode_ids)))
