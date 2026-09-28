#!/usr/bin/env python3
from __future__ import annotations

import functools

from ai.claude_code import ai_client
from ai.claude_code.ai_client import EPISODE_EFFORT, EPISODE_MODEL
from db.schema import Session, Stamp
from ai.time_keeper import main as _main


def _with_usage_summary(func):
    """ループの終わりに Claude Code の呼び出し回数・トークン・費用を出す(例外時も)。"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            print(f"[claude_ai] {ai_client.usage_summary()}")
    return wrapper


@_with_usage_summary
def loop_time(start_time: Stamp | None = None, max_days: int | None = None) -> Stamp:
    return _main.loop_time(ai_client, start_time, max_days)


def time_process(s: Session, time: Stamp):
    return _main.time_process(s, time, ai_client)


def claude_main(year: int | None = None, max_days: int | None = None) -> Stamp:
    return loop_time(Stamp(year) if year is not None else None, max_days)


@_with_usage_summary
def loop_time_for_story(story_id: int, years: int = 5) -> Stamp:
    return _main.loop_time_for_story(ai_client, story_id, years)


claude_story_years_main = loop_time_for_story


@_with_usage_summary
def daily_event(character_id: int | None = None, age: int | None = None, *,
                shared_style_extra: str = "", style_extra: str = "") -> int | None:
    return _main.daily_event(ai_client, character_id, age,
                             shared_style_extra=shared_style_extra, style_extra=style_extra)


claude_daily_event_main = daily_event


@_with_usage_summary
def place_event(place_id: int, time: Stamp | str, key: str, *,
                shared_style_extra: str = "", style_extra: str = "") -> int | None:
    return _main.place_event(ai_client, place_id, time, key,
                             shared_style_extra=shared_style_extra, style_extra=style_extra)


claude_place_event_main = place_event


def _writer_options(model: str | None, effort: str | None) -> dict:
    return {"model": model or EPISODE_MODEL, "effort": effort or EPISODE_EFFORT}


@_with_usage_summary
def write_episode(
    story_id: int, key: str | None, time: Stamp | str | None, character_ids: list[int],
    previous_episode_ids: list[int] | None = None, *, place_id: int | None = None,
    viewpoint: str | None = None, episode_id: int | None = None,
    model: str | None = None, effort: str | None = None,
    shared_style_extra: str = "", style_extra: str = "",
) -> int | None:
    """`model` / `effort` は本文を書く呼び出しにだけ効く。省けば fable の high"""
    return _main.write_episode(
        ai_client, story_id, key, time, character_ids, previous_episode_ids,
        place_id=place_id, viewpoint=viewpoint, episode_id=episode_id,
        writer_options=_writer_options(model, effort),
        shared_style_extra=shared_style_extra, style_extra=style_extra)


claude_write_episode_main = write_episode


@_with_usage_summary
def fill_episode(
    episode_id: int, character_ids: list[int], previous_episode_ids: list[int] | None = None, *,
    place_id: int | None = None, model: str | None = None, effort: str | None = None,
    shared_style_extra: str = "", style_extra: str = "",
) -> int | None:
    """話の枠に本文だけを書く。`model` / `effort` を省けば fable の high"""
    return _main.fill_episode(
        ai_client, episode_id, character_ids, previous_episode_ids,
        place_id=place_id, writer_options=_writer_options(model, effort),
        shared_style_extra=shared_style_extra, style_extra=style_extra)


claude_fill_episode_main = fill_episode


if __name__ == "__main__":
    year = int(input("year>>"))
    loop_time(Stamp(year))
