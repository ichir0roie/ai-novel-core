#!/usr/bin/env python3
"""作者が決めた種(`key`)・時刻・登場人物・前の話・作品から、話(`Plot`)を一話ぶん足す。

話の枠(種・時刻・視点・場所)を決め、本文は `episode_generator` で分けて書いて `Episode` に持つ。
`story_writer` は作品の中で本文の入っている最後の話の次を、世界の断面から書く。
"""
from __future__ import annotations

import json

from ai.time_keeper import episode_generator
from ai.time_keeper import event_progression_generator as progression
from ai.time_keeper._ai import AIClient
from ai.time_keeper._format import format_time
from data_access_logic.query import common_query
from db.schema import Plot, Location, Session, Stamp
from db.stamp import StampError

_FRAME_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの構成を考える作家です。
作品・直前の話・登場人物・作者の指定を渡すので、この作品の次の一話の枠(題・種・時刻・視点・場所)を決めて JSON で答えてください。
種(key)は本文を書く前の作者のメモです。300〜500 字を目安に、「## 場面」(番号付きの箇条書き。一行は「場所 / 出る人 / そこで変わること」)と「## 狙い」(この話で読者に伝えたいこと・変わること)の二つの節で書いてください。
直前の話は概要で渡します。その続きとして自然に立つ話にし、直前の話をなぞり直さないでください。
「この時点より後に既に決まっている出来事」を渡したときは、それと矛盾させず、そこで起きることを先回りしないでください。
作者の指定があるときは、それを核にして足りないところを補ってください。決まっていると書いた値は変えないでください。
時刻(start)は「年/月/日」の形で、直前の話より後、作品の期間の中から選んでください。
キーは title(サブタイトル。短く)・key(種)・start(時刻)・viewpoint(視点。誰に寄って語るか)・place(場所。自由記述)の五つだけ。"""

_FRAME_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "key": {"type": "string"},
        "start": {"type": "string"},
        "viewpoint": {"type": "string"},
        "place": {"type": "string"},
    },
    "required": ["title", "key", "start", "viewpoint", "place"],
    "additionalProperties": False,
}


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


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _frame_hint_lines(hints: dict) -> list[str]:
    """時刻(start)は決まった値として別に渡すので、ここでは扱わない。"""
    labels = {"title": "題", "key": "種", "end": "終わりの時刻(決まっている)", "viewpoint": "視点", "place": "場所"}
    return [f"作者の指定 {labels[field]}: {str(hints[field]).strip()}"
            for field in labels if str(hints.get(field) or "").strip()]


def generate_frame(
    session: Session, ai: AIClient, story_id: int, hints: dict | None = None,
    character_ids: list[int] | None = None, previous_plot_ids: list[int] | None = None, *,
    plot_id: int | None = None,
) -> Plot:
    """作者の下書き(`hints`。GUI の欄の値)を核に、本文の無い話の枠を一つ決めて足す(`plot_id` を渡せばその枠へ書く)。

    題・種・視点・場所は下書きを核に AI が組み立て直し、時刻は下書きにあればそれを、無ければ AI が直前の話の後から選ぶ。
    本文は書かない(`episode_generator.generate` で別に書く)。
    """
    hints = dict(hints or {})
    story = common_query.get_story(session, story_id)
    slot = episode_generator.frame(session, plot_id, story_id) if plot_id is not None else None
    fixed_time = Stamp.parse(hints.get("start")) or (slot.start if slot else None)
    characters = episode_generator.characters(session, character_ids or [])

    previous = [e for e in episode_generator._previous_plots(
        session, story.id, fixed_time or Stamp(99999, 12, 31), previous_plot_ids)
        if slot is None or e.id != slot.id]
    context_time = fixed_time or (previous[-1].start if previous and previous[-1].start else None) \
        or story.start or Stamp(1)
    recap = episode_generator._recap(session, previous, ai)
    cast = episode_generator._cast(session, characters, context_time, ai) if characters else []
    later_events = progression._later_events(session, story.place_id, characters, context_time, ai)
    context_place = session.get(Location, story.place_id) if story.place_id else None

    lines = [
        f"作品: {_dump(episode_generator._story_row(story))}",
        f"作品の期間: {story.start or '(不定)'}〜{story.end or '(不定)'}",
        f"作品の立つ場所: {_dump(episode_generator._place_row(context_place))}",
        f"直前の話(古い順): {_dump(recap['plots']) if recap['plots'] else '(無し。これが最初の話)'}",
    ]
    if cast:
        lines.append(f"登場人物: {_dump(cast)}")
    if later_events:
        lines.append(f"この時点より後に既に決まっている出来事: {_dump(later_events)}")
    if fixed_time is not None:
        lines.append(f"作者の指定 時刻(決まっている): {fixed_time}")
    lines += _frame_hint_lines(hints)
    lines.append("この作品の次の一話の枠を決めてください。")

    decided = ai.try_generate_json("\n".join(lines), _FRAME_SCHEMA, system=_FRAME_SYSTEM_PROMPT)
    key = (decided.get("key") or "").strip()
    if not key:
        raise ValueError("種(key)が得られなかった")
    time = fixed_time
    if time is None:
        try:
            time = Stamp.parse(decided.get("start"))
        except StampError:
            time = None
        if time is None:
            raise ValueError(f"時刻が決まらなかった(AI の答え: {decided.get('start')!r})。start を渡す")

    record = slot
    if record is None:
        record = Plot(story_id=story.id, title="")
        session.add(record)
    record.title = (decided.get("title") or "").strip()
    record.key = key
    record.start = time
    record.end = Stamp.parse(hints.get("end")) or record.end
    record.viewpoint = (decided.get("viewpoint") or "").strip() or None
    record.place = (decided.get("place") or "").strip() or None
    record.synced = False
    session.commit()
    print(f"[time_keepr/plot] {story.name}(id={story.id}) {format_time(time)}「{record.title}」 id={record.id} の枠を決めた")
    return record
