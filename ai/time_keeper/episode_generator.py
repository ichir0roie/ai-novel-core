#!/usr/bin/env python3
"""話の枠(種・時刻・視点・場所)と登場人物・前の話・作品から、話の本文(`Episode.text`)を書く。

材料は呼び出し側が名指しし、登場人物それぞれの直近の出来事と、
その時点より後に既に決まっている出来事を渡して、人物の側の時の流れと矛盾させない。
枠ごと足すときは `frame_generator` から呼ぶ。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ai.instructions import style
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.style import layout_novel_text
from ai.time_keeper import constants
from ai.time_keeper import event_progression_generator as progression
from ai.time_keeper import episode_summary, event_summary, idea_context
from ai.time_keeper._ai import AIClient
from ai.time_keeper._format import format_time
from ai.time_keeper.character_event_generator import _sheet
from data_access_logic.query import common_query
from db.schema import Character, ConfirmStatus, Episode, Event, Location, Session, Stamp, Story

def _system_prompt(*, shared_style_extra: str = "", style_extra: str = "") -> str:
    return f"""\
あなたは日本語のライトノベルを書く作家です。
作品・この話の種・時刻・場所・登場人物・直前の話を渡すので、この作品の話を一話ぶん書いてください。
種(key)は作者が決めたこの話の中身です。それを場面まで展開したものを本文にし、種に無い出来事を足さないでください。
直前の話は本文の代わりに概要(summary)で渡します。概要の筋をそのまま受け継ぎ、文体の覚え書きを渡したときはそれに揃えてください。
登場人物それぞれの直近の出来事は、この話の前に済んだことです。なぞり直さず、その後の人物として書いてください。
「この時点より後に既に決まっている出来事」を渡したときは、それと矛盾させず、そこで起きることを先回りして書かないでください。
「関係する設定」を渡したときは、それを踏まえて書いてください。
{EVENT_AGE_INSTRUCTION}
{style.style_instruction("episode", shared_extra=shared_style_extra, extra=style_extra)}
JSON で答えてください。キーは title(サブタイトル。短く)・viewpoint(視点人物の名前。視点を渡したときはそれ)・text(本文)の三つだけ。"""


# 文体の好み(舞台設定・既存の話から抽出した文体の癖など)を渡さない既定の文面。
_SYSTEM_PROMPT = _system_prompt()

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


def characters(session: Session, character_ids: list[int]) -> list[Character]:
    """話の登場人物として使えるのは、ユーザが確かめた(`confirmed=承認`)人物・対象だけ。"""
    characters = []
    for character_id in dict.fromkeys(int(i) for i in character_ids):
        character = session.get(Character, character_id)
        if character is None:
            raise ValueError(f"人物 id={character_id} が見つからない")
        if character.confirmed != ConfirmStatus.APPROVED:
            raise ValueError(
                f"人物 id={character_id}({character.name})はまだ確かめていない"
                f"(confirmed={character.confirmed})。GUI のレビュー画面で確かめてから話に使う")
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
        elif episode.text.strip():
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
    """話に使うのは、ユーザが確かめた(`confirmed=承認`)出来事だけ。"""
    if place_id is None:
        return []
    query = common_query.events_of_place_select(
        place_id, until=time, limit=constants.EPISODE_PLACE_EVENT_LIMIT
    ).where(Event.confirmed == ConfirmStatus.APPROVED)
    return list(reversed(session.scalars(query).all()))


def _cast(session: Session, characters: list[Character], time: Stamp, ai: AIClient) -> list[dict]:
    rows = []
    for character in characters:
        recent_query = common_query.events_of_character_select(
            character.id, until=time, limit=constants.EPISODE_CHARACTER_EVENT_LIMIT
        ).where(Event.confirmed == ConfirmStatus.APPROVED)
        recent = session.scalars(recent_query).all()
        rows.append({
            **_sheet(character, time),
            "relations": progression._relations(session, character, time),
            "recent_events": _event_rows(session, list(reversed(recent)), ai),
        })
    return rows


@dataclass
class Written:
    title: str
    viewpoint: str | None
    text: str
    linked: list = field(default_factory=list)


def write(
    session: Session, ai: AIClient, story: Story, key: str, time: Stamp, characters: list[Character],
    previous_episode_ids: list[int] | None = None, *, place: Location | None = None,
    viewpoint: str | None = None, exclude_episode_id: int | None = None, writer_options: dict | None = None,
    shared_style_extra: str = "", style_extra: str = "",
) -> Written | None:
    """本文を書くだけで、話の行には書き込まない(材料の要約だけは作って残す)。

    `place` を省くと作品の立つ場所を材料に使う。`exclude_episode_id` は前の話から外す話(書き込む先の枠)。
    `shared_style_extra` / `style_extra` は、世界の舞台設定・既存の話から抽出した文体の癖のような、
    世界ごとの好みを呼び出し側(親リポジトリ側)から渡す。
    """
    context_place_id = place.id if place is not None else story.place_id
    context_place = place or (session.get(Location, story.place_id) if story.place_id else None)

    previous = [e for e in _previous_episodes(session, story.id, time, previous_episode_ids)
                if e.id != exclude_episode_id]
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
        lines.append(idea_context.prompt_section(context.related, context.called, time))
    if viewpoint:
        lines.append(f"視点: {viewpoint}")
    lines.append(f"この話の種(これを場面まで展開する。種に無い出来事を足さない): {key}")

    system_prompt = (_system_prompt(shared_style_extra=shared_style_extra, style_extra=style_extra)
                     if (shared_style_extra or style_extra) else _SYSTEM_PROMPT)
    decided = ai.try_generate_json(
        "\n".join(lines), _SCHEMA, system=system_prompt, timeout=constants.EPISODE_TIMEOUT,
        **(writer_options or {}))
    text = layout_novel_text(decided.get("text") or "")
    if not text:
        print(f"[time_keepr/episode] {story.name}: 本文が得られなかった")
        return None
    return Written(title=(decided.get("title") or "").strip(),
                   viewpoint=(decided.get("viewpoint") or "").strip() or None,
                   text=text, linked=context.linked)


def attach(session: Session, record: Episode, written: Written, writer_options: dict | None = None) -> Episode:
    """書いた本文を話に付けて確定する。枠の空いている題・視点は本文を書いたときのもので埋める。

    自動生成なので `synced` を立てる(`schema.py` の `Episode.synced` の注記どおり)。
    """
    options = writer_options or {}
    record.title = (record.title or "").strip() or written.title
    record.viewpoint = record.viewpoint or written.viewpoint
    record.synced = True
    record.text = written.text
    record.model, record.effort = options.get("model"), options.get("effort")
    session.flush()
    idea_context.link(session, record, written.linked)
    session.commit()
    print(f"[time_keepr/episode] {format_time(record.start)}「{record.title}」 "
          f"id={record.id} {record.letters}字")
    return record


_DRAFT_FIELDS = ("title", "key", "viewpoint", "place")


def save_draft(session: Session, record: Episode, draft: dict) -> None:
    """AI 呼び出し(数分〜十数分かかることがある)の前に、作者の下書きの値でレコードを一度保存しておく。

    途中で失敗しても、GUI やスキルの呼び出し元がまだ確定していなかった題・種・視点・場所・時刻の
    編集を失わないようにする。`text`(本文)は AI が書く対象なので、呼び出し側が `draft` から外しておくこと。
    """
    for field in _DRAFT_FIELDS:
        value = (draft.get(field) or "").strip()
        if value:
            setattr(record, field, value)
    start = Stamp.parse(draft.get("start"))
    if start is not None:
        record.start = start
    end = Stamp.parse(draft.get("end"))
    if end is not None:
        record.end = end
    session.commit()


def frame(session: Session, episode_id: int, story_id: int | None = None) -> Episode:
    """本文を書き込む枠。本文の入っている話は書き換えない。"""
    record = session.get(Episode, episode_id)
    if record is None:
        raise ValueError(f"話 id={episode_id} が見つからない")
    if story_id is not None and record.story_id != story_id:
        raise ValueError(f"話 id={episode_id} は作品 id={story_id} の話ではない")
    if record.text.strip():
        raise ValueError(f"話 id={episode_id} には本文が入っている")
    return record


def generate(
    session: Session, ai: AIClient, episode_id: int, character_ids: list[int],
    previous_episode_ids: list[int] | None = None, *, place_id: int | None = None,
    writer_options: dict | None = None, shared_style_extra: str = "", style_extra: str = "",
) -> Episode | None:
    """枠(`episode_id` の話)の種・時刻・視点で本文を書いて付ける。

    `writer_options` は本文を書く呼び出しにだけ渡す(Claude で本文だけ別のモデルにするため)。
    `place_id` を渡すと枠の場所もその名前にする。本文が得られなければ枠を変えずに None を返す。
    `shared_style_extra` / `style_extra` は `write` に渡す(世界ごとの文体の好み)。
    """
    record = frame(session, episode_id)
    if not (record.key or "").strip():
        raise ValueError(f"話 id={episode_id} の key(話の種)が空")
    if record.start is None:
        raise ValueError(f"話 id={episode_id} の start(話が立つ時刻)が空")
    if not character_ids:
        raise ValueError("character_ids(登場人物)が空")
    story = common_query.get_story(session, record.story_id)
    place = session.get(Location, place_id) if place_id is not None else None
    if place_id is not None and place is None:
        raise ValueError(f"場所 id={place_id} が見つからない")

    written = write(session, ai, story, record.key.strip(), record.start, characters(session, character_ids),
                    previous_episode_ids, place=place, viewpoint=record.viewpoint,
                    exclude_episode_id=record.id, writer_options=writer_options,
                    shared_style_extra=shared_style_extra, style_extra=style_extra)
    if written is None:
        return None
    if place is not None:
        record.place = place.name
    return attach(session, record, written, writer_options)
