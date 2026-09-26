#!/usr/bin/env python3
from __future__ import annotations

import random
import traceback

from ai.time_keeper import (
    character_event_generator, episode_generator, event_progression_generator, event_seed, meme,
    place_event_generator,
)
from data_access_logic.query import common_query, world_createion_query
from db.schema import Session, Stamp, Story, get_env_session
from ai.time_keeper import (
    random_character_generator,
)
from ai.time_keeper._ai import AIClient
from ai.time_keeper._export import export_step
from ai.time_keeper._format import add_days, add_years, days_between, format_time


def loop_time(
    ai: AIClient, start_time: Stamp | None = None, max_days: int | None = None,
) -> Stamp:
    if start_time is None:
        with get_env_session() as s:
            start_time = s.scalar(
                common_query.latest_time_select()
            ) or Stamp(1)
    current_time = start_time
    days_done = 0

    while True:
        if max_days is not None and days_done >= max_days:
            print(f"[time_keepr] {format_time(current_time)} で "
                  f"{max_days} 日ぶん進めて区切る")
            return current_time
        print(f"[time_keepr] {format_time(current_time)}")
        with get_env_session() as s:
            active_stories = s.scalar(
                world_createion_query.active_story_count_select(current_time))
        if not active_stories:
            print(f"[time_keepr] {format_time(current_time)} をカバーする"
                  "作品が無い。CommitStory で作品を足すまでループを止める。")
            return current_time
        with get_env_session() as s:
            time_process(s, current_time, ai)
        # export_step(format_time(current_time))

        next_process_day = random.randint(1, 60)
        current_time = add_days(current_time, next_process_day)
        days_done += 1


def time_process(
    s: Session, time: Stamp, ai: AIClient,
):
    random_character_generator.generate_random(s, time, ai)
    event_progression_generator.generate_random(s, time, ai)


def daily_event(ai: AIClient, character_id: int | None = None, age: int | None = None) -> int | None:
    """ルーチンで起こした出来事は `CommitEvent` を通らないので、ミームもここで抜き出す(前の回の出来事が元になる)。"""
    with get_env_session() as s:
        meme.refresh(s, ai)
        event_seed.refresh(s, ai)
        event_seed.consolidate(s, ai)
        record = character_event_generator.generate_next(s, ai, character_id=character_id, age=age)
        return record.id if record is not None else None


def place_event(ai: AIClient, place_id: int, time: Stamp | str, key: str) -> int | None:
    time = Stamp.parse(time)
    with get_env_session() as s:
        meme.refresh(s, ai)
        event_seed.refresh(s, ai)
        event_seed.consolidate(s, ai)
        record = place_event_generator.generate_at(s, ai, place_id, time, key)
        return record.id if record is not None else None


def episode(
    ai: AIClient, story_id: int, key: str | None, time: Stamp | str | None, character_ids: list[int],
    previous_episode_ids: list[int] | None = None, *, place_id: int | None = None,
    viewpoint: str | None = None, writer_options: dict | None = None, episode_id: int | None = None,
) -> int | None:
    with get_env_session() as s:
        record = episode_generator.generate(
            s, ai, story_id, key, time, character_ids, previous_episode_ids,
            place_id=place_id, viewpoint=viewpoint, writer_options=writer_options, episode_id=episode_id)
        return record.id if record is not None else None


def loop_time_for_story(ai: AIClient, story_id: int, years: int = 5) -> Stamp:
    with get_env_session() as s:
        story = s.get(Story, story_id)
        if story is None:
            raise ValueError(f"作品 id={story_id} が見つからない")
        if story.start is None:
            raise ValueError(f"作品 id={story_id} に start が無い")
        start_time = story.start
    max_days = days_between(start_time, add_years(start_time, years))
    return loop_time(ai, start_time, max_days)
