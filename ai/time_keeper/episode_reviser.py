#!/usr/bin/env python3
"""すでに本文のある話(`Episode.text`)を、直す指示(`instruction`)に沿って書き直す。

材料の集め方(直前の話・登場人物・場所)は `episode_generator` と同じものを使い回す。
`episode_generator` と違い、話の筋そのものは変えず、指示にある観点だけを直す。
"""
from __future__ import annotations

from ai.instructions import style
from ai.instructions.event_writing import EVENT_AGE_INSTRUCTION
from ai.instructions.style import layout_novel_text
from ai.time_keeper import constants, episode_generator
from ai.time_keeper._ai import AIClient
from ai.time_keeper._format import format_time
from data_access_logic.query import common_query
from db.schema import Character, Episode, Location, Session, Story


def _system_prompt(*, shared_style_extra: str = "", style_extra: str = "") -> str:
    return f"""\
あなたは日本語のライトノベルを直す作家です。
作品・登場人物・直前の話・今の本文・直す指示を渡すので、指示に沿って今の本文を書き直してください。
筋(誰が何をしてどうなるか)は今の本文から変えず、指示にある観点だけを直してください。
直前の話は本文の代わりに概要(summary)で渡します。前の話の概要に出ていない登場人物は、この話が初登場です。
登場人物それぞれの直近の出来事は、この話の前に済んだことです。
{EVENT_AGE_INSTRUCTION}
{style.style_instruction("episode", shared_extra=shared_style_extra, extra=style_extra)}
JSON で答えてください。キーは title(サブタイトル。直さないなら空でよい)・text(書き直した本文)の二つだけ。"""


# 文体の好み(舞台設定・既存の話から抽出した文体の癖など)を渡さない既定の文面。
_SYSTEM_PROMPT = _system_prompt()

_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "text": {"type": "string"},
    },
    "required": ["text"],
    "additionalProperties": False,
}


def revise(
    session: Session, ai: AIClient, story: Story, record: Episode, characters: list[Character],
    instruction: str, previous_episode_ids: list[int] | None = None, *, place: Location | None = None,
    writer_options: dict | None = None, shared_style_extra: str = "", style_extra: str = "",
) -> episode_generator.Written | None:
    """`record` の今の本文を `instruction` に沿って書き直す。話への書き込みは呼び出し側(`generate`)が行う。"""
    context_place = place or (session.get(Location, story.place_id) if story.place_id else None)

    previous = [e for e in episode_generator._previous_episodes(session, story.id, record.start, previous_episode_ids)
                if e.id != record.id]
    print(f"[time_keepr/episode_revise] {story.name}(id={story.id}) 話 id={record.id} を推敲: "
          f"登場人物 {', '.join(c.name or '?' for c in characters)}")
    recap = episode_generator._recap(session, previous, ai)
    cast = episode_generator._cast(session, characters, record.start, ai)

    lines = [
        f"作品: {episode_generator._dump(episode_generator._story_row(story))}",
        f"時刻: {record.start}",
        f"場所: {episode_generator._dump(episode_generator._place_row(context_place))}",
        f"直前の話(古い順): {episode_generator._dump(recap['episodes']) if recap['episodes'] else '(無し)'}",
    ]
    if recap["style"]:
        lines.append(f"直前の話の文体(これに揃える): {recap['style']}")
    lines.append(f"登場人物: {episode_generator._dump(cast)}")
    lines.append(f"今の題: {record.title or '(無し)'}")
    lines.append(f"今の本文: {record.text}")
    lines.append(f"直す指示: {instruction.strip()}")

    system_prompt = (_system_prompt(shared_style_extra=shared_style_extra, style_extra=style_extra)
                     if (shared_style_extra or style_extra) else _SYSTEM_PROMPT)
    decided = ai.try_generate_json(
        "\n".join(lines), _SCHEMA, system=system_prompt, timeout=constants.EPISODE_TIMEOUT,
        **(writer_options or {}))
    text = layout_novel_text(decided.get("text") or "")
    if not text:
        print(f"[time_keepr/episode_revise] {story.name}: 本文が得られなかった")
        return None
    return episode_generator.Written(
        title=(decided.get("title") or "").strip() or record.title, text=text)


def _append_instruction_to_key(key: str, instruction: str) -> str:
    """推敲の指示をキーテキストの末尾に書き足す。あとで見返せるよう、指示を消さずに積む。"""
    heading = "## 推敲"
    bullet = f"- {instruction.strip()}"
    if heading in key:
        return f"{key.rstrip()}\n{bullet}\n"
    sep = "\n\n" if key.strip() else ""
    return f"{key.rstrip()}{sep}{heading}\n\n{bullet}\n"


def attach(session: Session, record: Episode, written: episode_generator.Written, instruction: str) -> Episode:
    """書き直した本文を話に付ける。手直しなので `episode_generator.attach` と違い `synced` は変えない。"""
    record.title = written.title or record.title
    record.text = written.text
    record.key = _append_instruction_to_key(record.key, instruction)
    session.commit()
    print(f"[time_keepr/episode_revise] {format_time(record.start)}「{record.title}」 "
          f"id={record.id} {record.letters}字")
    return record


def generate(
    session: Session, ai: AIClient, episode_id: int, character_ids: list[int], instruction: str,
    previous_episode_ids: list[int] | None = None, *, place_id: int | None = None,
    writer_options: dict | None = None, shared_style_extra: str = "", style_extra: str = "",
) -> Episode | None:
    """すでに本文のある話(`episode_id`)を、指示(`instruction`。必須)に沿って書き直す。

    `character_ids` はこの話に出る人物(初登場・既出とも)。前の話の概要に出ていない人物は、
    その材料から AI が初登場と判断して外見・性格の描写を厚くする。本文が空の話は止まる
    (先に `episode_generator.generate` で書く)。`place_id` を省くとこの話(`record.place_id`)の場所を使う。
    `shared_style_extra` / `style_extra` は `revise` に渡す。
    """
    record = session.get(Episode, episode_id)
    if record is None:
        raise ValueError(f"話 id={episode_id} が見つからない")
    if not record.text.strip():
        raise ValueError(f"話 id={episode_id} には本文が無い(先に episode_generator.generate で書く)")
    if not character_ids:
        raise ValueError("character_ids(登場人物)が空")
    if not instruction.strip():
        raise ValueError("instruction(直す指示)が空")
    story = common_query.get_story(session, record.story_id)
    characters = episode_generator.characters(session, character_ids)
    if place_id is None:
        place_id = record.place_id
    place = session.get(Location, place_id) if place_id is not None else None
    if place_id is not None and place is None:
        raise ValueError(f"場所 id={place_id} が見つからない")

    written = revise(session, ai, story, record, characters, instruction, previous_episode_ids, place=place,
                     writer_options=writer_options, shared_style_extra=shared_style_extra, style_extra=style_extra)
    if written is None:
        return None
    return attach(session, record, written, instruction)
