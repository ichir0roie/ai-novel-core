#!/usr/bin/env python3
"""行を確定したあと AI の段を追いかける流れ(`CommitEvent` / `UpdateEvent` / `CommitEpisode` / `CommitStory` / `CommitOracle` の `run()`)。

確定は db の段一つで済ませる(GUI の API が呼ぶ `execute(s)` と同じ)。そのあとの AI の段(ミームの抜き出し・要約・種・事実確認)は、
AI が答えなくても確定は残る。
"""
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.episode import steps as episode_steps
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.event import steps as event_steps
from data_access_logic.event.form import EventCreateForm, EventUpdateForm
from data_access_logic.event.record import EventRecord
from data_access_logic.oracle import steps as oracle_steps
from data_access_logic.oracle.form import OracleCreateForm
from data_access_logic.oracle.record import MemeSourceCommitted
from data_access_logic.step import RowId
from data_access_logic.story import steps as story_steps
from data_access_logic.story.form import StoryCreateForm
from data_access_logic.story.record import StoryRecord
from data_access_logic.flows import event_seed, fact_check, meme
from data_access_logic.caller import call
from data_access_logic.flows.summary import rewrite_episode_summaries, rewrite_event_summaries


def commit_episode(episode: EpisodeCommitForm, ai: AIClient = ai_client) -> EpisodeRecord:
    record = call(episode_steps.commit_episode, episode)
    meme.refresh(ai)
    rewrite_episode_summaries(ai, [record.id])
    return record


def commit_event(event: EventCreateForm, ai: AIClient = ai_client) -> EventRecord:
    record = call(event_steps.commit_event, event)
    meme.refresh(ai)
    rewrite_event_summaries(ai, [record.id])
    # 足した出来事自身の本文も種の元になる
    event_seed.refresh_and_consolidate(ai)
    return record


def update_event(event: EventUpdateForm, ai: AIClient = ai_client) -> EventRecord:
    record = call(event_steps.update_event, event)
    meme.refresh(ai)
    rewrite_event_summaries(ai, [record.id])
    return record


def commit_story(story: StoryCreateForm, ai: AIClient = ai_client) -> StoryRecord:
    """作品はミームの元ではなく、出来事の種の元なので、種を抜き出す。"""
    record = call(story_steps.commit_story, story)
    event_seed.refresh_and_consolidate(ai)
    return record


def _meme_source_follow_up(ai: AIClient, table: str, record_id: int, text: str, fact_check_enabled: bool) -> int:
    """確定したもの自身を検め、検証結果を足した本文からミームを抜き出し、足したミームも検める。足したミームの件数を返す。"""
    if fact_check_enabled and text.strip():
        fact_check.check(ai, table, ids=[record_id])
    return fact_check.extract_memes(ai, fact_check_enabled)


def commit_oracle(oracle: OracleCreateForm, fact_check: bool = True, ai: AIClient = ai_client) -> MemeSourceCommitted:
    committed = call(oracle_steps.commit_oracle, oracle)
    added = _meme_source_follow_up(ai, "oracle", committed.id, committed.text, fact_check)
    return MemeSourceCommitted(record=call(oracle_steps.oracle_record, RowId(id=committed.id)), memes_added=added)
