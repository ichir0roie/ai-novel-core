#!/usr/bin/env python3
from __future__ import annotations

from db.schema import Session, Stamp
from ai.local_ai import ai_client
from ai.time_keeper import main


def loop_time(start_time: Stamp | None = None, max_days: int | None = None) -> Stamp:
    return main.loop_time(ai_client, start_time, max_days)


def time_process(s: Session, time: Stamp):
    return main.time_process(s, time, ai_client)


def loop_time_for_story(story_id: int, years: int = 5) -> Stamp:
    return main.loop_time_for_story(ai_client, story_id, years)


def daily_event(character_id: int | None = None, age: int | None = None) -> int | None:
    return main.daily_event(ai_client, character_id, age)


def place_event(place_id: int, time: Stamp | str, key: str) -> int | None:
    return main.place_event(ai_client, place_id, time, key)


def episode(
    story_id: int, key: str | None, time: Stamp | str | None, character_ids: list[int],
    previous_episode_ids: list[int] | None = None, *, place_id: int | None = None,
    viewpoint: str | None = None, episode_id: int | None = None,
) -> int | None:
    return main.episode(ai_client, story_id, key, time, character_ids, previous_episode_ids,
                        place_id=place_id, viewpoint=viewpoint, episode_id=episode_id)


if __name__ == "__main__":
    year = int(input("year>>"))
    stamp = Stamp(
        year
    )

    loop_time(stamp)
