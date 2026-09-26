#!/usr/bin/env python3
"""作者が決めた種(`key`)・時刻・登場人物・前の話・作品から、話(`Episode`)を一話ぶん書いて足す。

`story_writer` は作品の中で本文の入っている最後の話の次を、世界の断面から書く。
こちらは材料を呼び出し側が名指しし、登場人物それぞれの直近の出来事と、
その時点より後に既に決まっている出来事を渡して、人物の側の時の流れと矛盾させない。
"""
from __future__ import annotations

import json

from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.style import EPISODE_STYLE_INSTRUCTION, EPISODE_TARGET_LETTERS, layout_novel_text
from ai.time_keeper import constants
from ai.time_keeper import event_progression_generator as progression
from ai.time_keeper import episode_summary, event_summary, idea_context
from ai.time_keeper._ai import AIClient
from ai.time_keeper._format import format_time
from ai.time_keeper.character_event_generator import _sheet
from data_access_logic.query import common_query
from db.schema import Character, Episode, Event, Location, Session, Stamp, Story

_SYSTEM_PROMPT = f"""\
あなたは日本語のライトノベルを書く作家です。
作品・この話の種・時刻・場所・登場人物・直前の話を渡すので、この作品の話を一話ぶん書いてください。
種(key)は作者が決めたこの話の中身です。それを場面まで展開したものを本文にし、種に無い出来事を足さないでください。
直前の話は本文の代わりに概要(summary)で渡します。概要の筋をそのまま受け継ぎ、文体の覚え書きを渡したときはそれに揃えてください。
登場人物それぞれの直近の出来事は、この話の前に済んだことです。なぞり直さず、その後の人物として書いてください。
「この時点より後に既に決まっている出来事」を渡したときは、それと矛盾させず、そこで起きることを先回りして書かないでください。
「関係する設定」を渡したときは、それを踏まえて書いてください。
{EVENT_AGE_INSTRUCTION}
{EPISODE_STYLE_INSTRUCTION}
JSON で答えてください。キーは title(サブタイトル。短く)・viewpoint(視点人物の名前。視点を渡したときはそれ)・text(本文)の三つだけ。"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "viewpoint": {"type": "string"},
        "text": {"type": "string"},
    },
    "required": ["title", "viewpoint", "text"],
    "additionalProperties": False,
}


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _story_row(story: Story) -> dict:
    return {"name": story.name, "narration": story.narration, "state": story.state, "text": story.text}


def _place_row(place: Location | None) -> dict | None:
    return {"name": place.name, "kind": place.kind, "text": place.text} if place else None


def _characters(session: Session, character_ids: list[int]) -> list[Character]:
    characters = []
    for character_id in dict.fromkeys(int(i) for i in character_ids):
        character = session.get(Character, character_id)
        if character is None:
            raise ValueError(f"人物 id={character_id} が見つからない")
        characters.append(character)
    return characters


def _previous_episodes(
    session: Session, story_id: int, time: Stamp, previous_episode_ids: list[int] | None,
) -> list[Episode]:
    """`previous_episode_ids` を省くと、作品の中で `time` より前の話を新しいほうから三つ取る。"""
    if previous_episode_ids is None:
        rows = session.scalars(common_query.episodes_select(
            story_id, count=constants.EPISODE_PREVIOUS_LIMIT, before=time)).all()
        return list(reversed(rows))
    episodes = []
    for episode_id in dict.fromkeys(int(i) for i in previous_episode_ids):
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise ValueError(f"話 id={episode_id} が見つからない")
        episodes.append(episode)
    return sorted(episodes, key=lambda e: (e.start is None, e.start or Stamp(1), e.id))


def _recap(session: Session, episodes: list[Episode], ai: AIClient) -> dict:
    """本文は写させないよう概要で渡す。概要が作れなかった話だけ本文のまま渡す。"""
    rows, styles = [], []
    for episode in episodes:
        row = {"id": episode.id, "title": episode.title,
               "start": str(episode.start) if episode.start else None}
        note = episode_summary.summarize(session, episode, ai) or {}
        if note.get("summary"):
            rows.append({**row, "summary": note["summary"]})
        elif (episode.text or "").strip():
            rows.append({**row, "text": episode.text})
        else:
            rows.append({**row, "key": episode.key})
        if note.get("style"):
            styles.append(note["style"])
    return {"episodes": rows, "style": styles[-1] if styles else ""}


def _event_rows(session: Session, events: list[Event], ai: AIClient) -> list[dict]:
    """本文は写させないよう要約で渡す。"""
    # 場所は noload の関連なので、要約の commit で期限切れになる前に全件ぶん組んでおく
    rows = [{"name": event.name, "start": str(event.start or event.time),
             "end": str(event.end) if event.end else None,
             "place": event.location.name if event.location else None} for event in events]
    for event, row in zip(events, rows):
        summary = event_summary.summarize(session, event, ai)
        if summary:
            row["summary"] = summary
    return rows


def _place_events(session: Session, place_id: int | None, time: Stamp) -> list[Event]:
    if place_id is None:
        return []
    return list(reversed(session.scalars(common_query.events_of_place_select(
        place_id, until=time, limit=constants.EPISODE_PLACE_EVENT_LIMIT)).all()))


def _cast(session: Session, characters: list[Character], time: Stamp, ai: AIClient) -> list[dict]:
    rows = []
    for character in characters:
        recent = session.scalars(common_query.events_of_character_select(
            character.id, until=time, limit=constants.EPISODE_CHARACTER_EVENT_LIMIT)).all()
        rows.append({
            **_sheet(character, time),
            "relations": progression._relations(session, character, time),
            "recent_events": _event_rows(session, list(reversed(recent)), ai),
        })
    return rows


def _slot(session: Session, story_id: int, episode_id: int | None) -> Episode | None:
    """本文の入る前の話(題・時刻だけ決めた枠)。本文のある話は書き換えない。"""
    if episode_id is None:
        return None
    slot = session.get(Episode, episode_id)
    if slot is None:
        raise ValueError(f"話 id={episode_id} が見つからない")
    if slot.story_id != story_id:
        raise ValueError(f"話 id={episode_id} は作品 id={story_id} の話ではない")
    if (slot.text or "").strip():
        raise ValueError(f"話 id={episode_id} には本文が入っている")
    return slot


def generate(
    session: Session, ai: AIClient, story_id: int, key: str | None, time: Stamp | str | None,
    character_ids: list[int], previous_episode_ids: list[int] | None = None, *,
    place_id: int | None = None, viewpoint: str | None = None, writer_options: dict | None = None,
    episode_id: int | None = None,
) -> Episode | None:
    """`writer_options` は本文を書く呼び出しにだけ渡す(Claude で本文だけ別のモデルにするため)。

    `place_id` を省くと作品の立つ場所を材料に使い、話の `place` は空のまま残す。
    `episode_id` を渡すと話を足さずにその枠へ書く。種・時刻・視点・題・場所は、省けば枠のものを使う。
    本文が得られなければ話を足さず(枠も変えず)に None を返す。
    """
    slot = _slot(session, story_id, episode_id)
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
    characters = _characters(session, character_ids)
    place = session.get(Location, place_id) if place_id is not None else None
    if place_id is not None and place is None:
        raise ValueError(f"場所 id={place_id} が見つからない")
    context_place_id = place.id if place is not None else story.place_id
    context_place = place or (session.get(Location, story.place_id) if story.place_id else None)

    previous = [e for e in _previous_episodes(session, story.id, time, previous_episode_ids)
                if slot is None or e.id != slot.id]
    print(f"[time_keepr/episode] {story.name}(id={story.id}) {format_time(time)} の話: "
          f"登場人物 {', '.join(c.name or '?' for c in characters)} / "
          f"前の話 {[e.id for e in previous] or '(無し)'}")
    recap = _recap(session, previous, ai)
    cast = _cast(session, characters, time, ai)
    place_events = _event_rows(session, _place_events(session, context_place_id, time), ai)
    later_events = progression._later_events(session, context_place_id, characters, time, ai)
    context = idea_context.gather(session, key, ai, context_place_id, time)

    lines = [
        f"作品: {_dump(_story_row(story))}",
        f"時刻: {time}",
        f"場所: {_dump(_place_row(context_place))}",
        f"直前の話(古い順): {_dump(recap['episodes']) if recap['episodes'] else '(無し)'}",
    ]
    if recap["style"]:
        lines.append(f"直前の話の文体(これに揃える): {recap['style']}")
    lines.append(f"登場人物: {_dump(cast)}")
    if place_events:
        lines.append(f"この場所の直近の出来事: {_dump(place_events)}")
    if later_events:
        lines.append(f"この時点より後に既に決まっている出来事: {_dump(later_events)}")
    if context.related:
        lines.append(idea_context.prompt_section(context.related, context.called))
    if viewpoint:
        lines.append(f"視点: {viewpoint}")
    lines += [
        f"この話の種(これを場面まで展開する。種に無い出来事を足さない): {key}",
        f"この話を{EPISODE_TARGET_LETTERS[0]}〜{EPISODE_TARGET_LETTERS[1]}字の本文に書いてください。",
    ]

    decided = ai.try_generate_json(
        "\n".join(lines), _SCHEMA, system=_SYSTEM_PROMPT, timeout=constants.EPISODE_TIMEOUT,
        **(writer_options or {}))
    text = layout_novel_text(decided.get("text") or "")
    if not text:
        print(f"[time_keepr/episode] {story.name}: 本文が得られなかったので話を足さない")
        return None

    title = (decided.get("title") or "").strip()
    viewpoint = viewpoint or (decided.get("viewpoint") or "").strip() or None
    if slot is None:
        record = Episode(story_id=story.id, title=title, place=place.name if place is not None else None)
        session.add(record)
    else:
        record = slot
        record.title = (record.title or "").strip() or title
        if place is not None:
            record.place = place.name
    record.key, record.start, record.text, record.letters = key, time, text, len(text)
    record.synced, record.viewpoint = True, viewpoint
    session.flush()
    idea_context.link(session, record, context.linked)
    session.commit()
    print(f"[time_keepr/episode] {story.name}「{record.title}」 id={record.id} {record.letters}字")
    return record
