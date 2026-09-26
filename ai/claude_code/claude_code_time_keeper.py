#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client, story_writer
from db.schema import Session, Stamp
from ai.time_keeper import main as _main


def loop_time(start_time: Stamp | None = None, max_days: int | None = None) -> Stamp:
    try:
        return _main.loop_time(ai_client, start_time, max_days)
    finally:
        print(f"[claude_ai] {ai_client.usage_summary()}")


def time_process(s: Session, time: Stamp):
    return _main.time_process(s, time, ai_client)


def claude_main(year: int | None = None, max_days: int | None = None) -> Stamp:
    return loop_time(Stamp(year) if year is not None else None, max_days)


def loop_time_for_story(story_id: int, years: int = 5) -> Stamp:
    try:
        return _main.loop_time_for_story(ai_client, story_id, years)
    finally:
        print(f"[claude_ai] {ai_client.usage_summary()}")


def claude_story_years_main(story_id: int, years: int = 5) -> Stamp:
    return loop_time_for_story(story_id, years)


def daily_event(character_id: int | None = None, age: int | None = None) -> int | None:
    try:
        return _main.daily_event(ai_client, character_id, age)
    finally:
        print(f"[claude_ai] {ai_client.usage_summary()}")


def claude_daily_event_main(character_id: int | None = None, age: int | None = None) -> int | None:
    return daily_event(character_id, age)


def place_event(place_id: int, time: Stamp | str, key: str) -> int | None:
    try:
        return _main.place_event(ai_client, place_id, time, key)
    finally:
        print(f"[claude_ai] {ai_client.usage_summary()}")


def claude_place_event_main(place_id: int, time: Stamp | str, key: str) -> int | None:
    return place_event(place_id, time, key)


def episode(
    story_id: int, key: str | None, time: Stamp | str | None, character_ids: list[int],
    previous_episode_ids: list[int] | None = None, *, place_id: int | None = None,
    viewpoint: str | None = None, episode_id: int | None = None,
) -> int | None:
    try:
        return _main.episode(
            ai_client, story_id, key, time, character_ids, previous_episode_ids,
            place_id=place_id, viewpoint=viewpoint, episode_id=episode_id,
            writer_options={"model": story_writer.EPISODE_MODEL, "effort": story_writer.EPISODE_EFFORT})
    finally:
        print(f"[claude_ai] {ai_client.usage_summary()}")


def claude_episode_main(
    story_id: int, key: str | None, time: Stamp | str | None, character_ids: list[int],
    previous_episode_ids: list[int] | None = None, *, place_id: int | None = None,
    viewpoint: str | None = None, episode_id: int | None = None,
) -> int | None:
    return episode(story_id, key, time, character_ids, previous_episode_ids,
                   place_id=place_id, viewpoint=viewpoint, episode_id=episode_id)


if __name__ == "__main__":
    year = int(input("year>>"))
    loop_time(Stamp(year))
