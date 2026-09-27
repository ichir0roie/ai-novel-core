#!/usr/bin/env python3
"""作者が決めた種(`key`)・時刻・登場人物・前の話・作品から、話(`Plot`)を一話ぶん足す。

話の枠(種・時刻・視点・場所)を決め、本文は `episode_generator` で分けて書いて `Episode` に持つ。
`story_writer` は作品の中で本文の入っている最後の話の次を、世界の断面から書く。
"""
from __future__ import annotations

from ai.time_keeper import episode_generator
from ai.time_keeper._ai import AIClient
from data_access_logic.query import common_query
from db.schema import Plot, Location, Session, Stamp


def generate(
    session: Session, ai: AIClient, story_id: int, key: str | None, time: Stamp | str | None,
    character_ids: list[int], previous_plot_ids: list[int] | None = None, *,
    place_id: int | None = None, viewpoint: str | None = None, writer_options: dict | None = None,
    plot_id: int | None = None, shared_style_extra: str = "", style_extra: str = "",
) -> Plot | None:
    """`writer_options` は本文を書く呼び出しにだけ渡す(Claude で本文だけ別のモデルにするため)。

    `place_id` を省くと作品の立つ場所を材料に使い、話の `place` は空のまま残す。
    `plot_id` を渡すと話を足さずにその枠へ書く。種・時刻・視点・題・場所は、省けば枠のものを使う。
    本文が得られなければ話を足さず(枠も変えず)に None を返す。
    `shared_style_extra` / `style_extra` は `episode_generator.write` に渡す(世界ごとの文体の好み)。
    """
    slot = episode_generator.frame(session, plot_id, story_id) if plot_id is not None else None
    key = (key or (slot.key if slot else "") or "").strip()
    if not key:
        raise ValueError("key(話の種)が空")
    time = Stamp.parse(time) if time else (slot.start if slot else None)
    if time is None:
        raise ValueError("time(話が立つ時刻)が空")
    viewpoint = viewpoint or (slot.viewpoint if slot else None)
    if not character_ids:
        raise ValueError("character_ids(登場人物)が空")
    story = common_query.get_story(session, story_id)
    characters = episode_generator.characters(session, character_ids)
    place = session.get(Location, place_id) if place_id is not None else None
    if place_id is not None and place is None:
        raise ValueError(f"場所 id={place_id} が見つからない")

    written = episode_generator.write(
        session, ai, story, key, time, characters, previous_plot_ids, place=place, viewpoint=viewpoint,
        exclude_plot_id=slot.id if slot else None, writer_options=writer_options,
        shared_style_extra=shared_style_extra, style_extra=style_extra)
    if written is None:
        print(f"[time_keepr/episode] {story.name}: 本文が得られなかったので話を足さない")
        return None

    record = slot
    if record is None:
        record = Plot(story_id=story.id, title="")
        session.add(record)
    if place is not None:
        record.place = place.name
    record.key, record.start, record.viewpoint = key, time, viewpoint
    episode_generator.attach(session, record, written, writer_options)
    return record
