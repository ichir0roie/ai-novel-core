#!/usr/bin/env python3
"""`local_ai` には本文を書く生成器が無いので、ここだけは claude_ai 固有。
自動生成なので `synced` は立てて確定する(`schema.py` の `Episode.synced` の注記どおり)。
"""
from __future__ import annotations

import json

from ai.instructions import style
from ai.instructions.style import layout_novel_text
from ai.claude_code import ai_client
from ai.claude_code.interface.story import _rows
from ai.time_keeper import episode_summary, idea_context
from data_access_logic.query import common_query
from db.schema import Episode, Session, get_env_session

# 一話ぶんの本文を書かせるので、断片の JSON より長く待つ。
EPISODE_TIMEOUT = 900.0

# 本文の代わりに概要で渡す、直前の話の本数。文体の覚え書きは一番新しい話のものを使う。
RECAP_EPISODE_LIMIT = 3

def _system_prompt(*, shared_style_extra: str = "", style_extra: str = "") -> str:
    return f"""\
あなたは日本語のライトノベルを書く作家です。
作品の見出し・直前の話・世界の断面・顔ぶれを渡すので、この作品の次の話を一話ぶん書いてください。
直前の話は本文の代わりに概要(summary)で渡します。概要の筋をそのまま受け継ぎ、文体の覚え書きを渡したときはそれに揃えてください。
{style.style_instruction("episode", shared_extra=shared_style_extra, extra=style_extra)}
種(key)を渡したときは、それを場面まで展開したものを本文にしてください。種に無い出来事を足さないでください。
「関係する設定」を渡したときは、それを踏まえて書いてください。
JSON で答えてください。キーは title(サブタイトル。短く)と text(本文)の二つだけ。"""


# 文体の好み(舞台設定・既存の話から抽出した文体の癖など)を渡さない既定の文面。
_SYSTEM_PROMPT = _system_prompt()

_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "text": {"type": "string"},
    },
    "required": ["title", "text"],
    "additionalProperties": False,
}


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _ordered(session: Session, story_id: int) -> list[Episode]:
    return list(session.scalars(common_query.story_episodes_select(story_id)).all())


def _target_index(rows: list[Episode], episode_id: int | None) -> int:
    """書く話の位置。`episode_id` を省くと、本文の入っている最後の話の次。
    その位置に種だけの話があればそれを埋め、無ければ末尾に新しい話を足す(len(rows) を返す)。
    """
    if episode_id is not None:
        for index, record in enumerate(rows):
            if record.id == int(episode_id):
                return index
        raise ValueError(f"id={episode_id} という話がこの作品に無い")
    written = [index for index, record in enumerate(rows) if record.text.strip()]
    return (written[-1] + 1) if written else 0


def _blocking_unsynced(rows: list[Episode], index: int) -> list[dict]:
    """本文がまだ無い話(種だけ入れてある先の話)は、書きようがないので数えない。"""
    return [{"id": record.id, "title": record.title} for record in rows[:index]
            if record.text.strip() and not record.synced]


def _episode_recap(session: Session, episode: dict) -> dict:
    record = session.get(Episode, episode["id"])
    return episode_summary.summarize(session, record, ai_client) or {}


def _recap(session: Session, episodes: list[dict]) -> dict:
    rows, styles = [], []
    for episode in episodes:
        if not (episode.get("text") or "").strip():
            rows.append(episode)
            continue
        note = _episode_recap(session, episode)
        if note.get("summary"):
            rows.append({**{k: v for k, v in episode.items() if k != "text"}, "summary": note["summary"]})
        else:
            rows.append(episode)
        if note.get("style"):
            styles.append(note["style"])
    return {"episodes": rows, "style": styles[-1] if styles else ""}


def _materials(
    session: Session, story_id: int, time, *,
    rows: list[Episode], index: int, recap_count: int, count: int, reach: int, levels: int,
) -> dict:
    story = common_query.get_story(session, story_id)
    unsynced = _blocking_unsynced(rows, index)
    result = {
        "story": _rows.story_digest(session, story),
        "unsynced": unsynced,
        "stopped": bool(unsynced),
    }
    if result["stopped"]:
        return result
    if story.place_id is None:
        raise ValueError(f"作品 {story.name} に立つ場所(place_id)が無い")
    _, until = common_query.resolve_time(session, time, story)
    result["time"] = str(until)
    result["episodes"] = [_rows.episode_row(record) for record in rows[max(0, index - recap_count):index]]
    result["cast"] = _rows.cast(session, story_id, until, count=count, levels=levels)
    result["brief"] = _rows.brief(session, story.place_id, until, reach=reach)
    return result


def write_next_episode(
    session: Session, story_id: int, time=None, *, episode_id: int | None = None,
    recap_count: int = RECAP_EPISODE_LIMIT, count: int = 5, reach: int = 60, levels: int = 1,
    shared_style_extra: str = "", style_extra: str = "",
) -> Episode | None:
    story_row = common_query.get_story(session, story_id)
    rows = _ordered(session, story_id)
    index = _target_index(rows, episode_id)

    materials = _materials(session, story_id, time, rows=rows, index=index,
                           recap_count=recap_count, count=count, reach=reach, levels=levels)
    story = materials["story"]
    if materials["stopped"]:
        print(f"[claude_ai/story] {story['name']}: 未同期の話 {materials['unsynced']} が残っているので書かない")
        return None

    record = rows[index] if index < len(rows) else None
    seed = (record.key or "").strip() if record is not None else ""
    context = (idea_context.gather(session, seed, ai_client, story_row.place_id, materials["time"])
               if seed else idea_context.IdeaContext())
    recap = _recap(session, materials["episodes"])
    lines = [
        f"作品: {_dump(story)}",
        f"時刻: {materials['time']}",
        f"直前の話(古い順): {_dump(recap['episodes']) if recap['episodes'] else '(無し。第一話)'}",
    ]
    if recap["style"]:
        lines.append(f"直前の話の文体(これに揃える): {recap['style']}")
    lines += [
        f"顔ぶれ: {_dump(materials['cast'])}",
        f"世界の断面: {_dump(materials['brief'])}",
    ]
    if seed:
        lines.append(f"この話の種(これを場面まで展開する。種に無い出来事を足さない): {seed}")
    if context.related:
        lines.append(idea_context.prompt_section(context.related, context.called))
    if record is not None and (record.viewpoint or record.place):
        lines.append(f"視点と場所: {record.viewpoint or ''} / {record.place or ''}")
    lines.append("この作品の次の話を書いてください。")

    system_prompt = (_system_prompt(shared_style_extra=shared_style_extra, style_extra=style_extra)
                     if (shared_style_extra or style_extra) else _SYSTEM_PROMPT)
    decided = ai_client.try_generate_json(
        "\n".join(lines), _SCHEMA, system=system_prompt, timeout=EPISODE_TIMEOUT,
        model=ai_client.EPISODE_MODEL, effort=ai_client.EPISODE_EFFORT)
    text = layout_novel_text(decided.get("text") or "")
    if not text:
        print(f"[claude_ai/story] {story['name']}: 本文が得られなかったので見送り")
        return None
    title = (decided.get("title") or "").strip()

    if record is None:
        record = Episode(story_id=story_id, title=title, synced=True)
        session.add(record)
    else:
        record.title = title or record.title
        record.synced = True
    record.text = text
    record.model = ai_client.EPISODE_MODEL
    record.effort = ai_client.EPISODE_EFFORT
    session.flush()
    idea_context.link(session, record, context.linked)
    session.commit()
    print(f"[claude_ai/story] {story_row.name}「{record.title}」"
          f" id={record.id} {record.letters}字")
    return record


def write_story(story_id: int, episodes_to_write: int = 1, time=None,
                episode_id: int | None = None, *,
                shared_style_extra: str = "", style_extra: str = "") -> list[Episode]:
    """`episode_id` は一話目にだけ効く。二話目からは、本文の入っている最後の話の次を書く"""
    written: list[Episode] = []
    with get_env_session() as session:
        for offset in range(episodes_to_write):
            target = episode_id if offset == 0 else None
            record = write_next_episode(session, story_id, time, episode_id=target,
                                        shared_style_extra=shared_style_extra, style_extra=style_extra)
            if record is None:
                break
            written.append(record)
    print(f"[claude_ai] {ai_client.usage_summary()}")
    return written
