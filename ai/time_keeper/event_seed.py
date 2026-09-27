#!/usr/bin/env python3
from __future__ import annotations

import random
import re

from sqlalchemy import select

from ai.time_keeper import constants
from ai.time_keeper._ai import AIClient
from data_access_logic.query import event_seed_query
from db.schema import Character, Episode, Event, EventSeed, Session, Story

_SYSTEM_PROMPT = """\
あなたは物語の編集者です。
作品の筋書き・話の骨組み・人物の筋書き・起きた出来事をいくつか番号つきで渡すので、それぞれから、ほかの時代・ほかの場所・ほかの人物にも起こせる「出来事の種」を抜き出してください。
- 人名・地名・組織名・その作品だけの用語と、年代を抜く。人物は「古参の番兵」「商家の娘」のような立場で書く。
- 一つの種は一〜二文。誰が、何をきっかけに、何をして、どんな揺れや変化が起きるかを書く。
- 作者の前書き・使用環境・書き方の約束・構成表など、出来事にならない文からは抜き出さない。
- 一つの元から 0〜3 件。同じ元の中で似た種は一つにまとめる。
JSON で答えてください。キーは seeds(種の文字列のリスト)だけ。"""

_CONSOLIDATE_SYSTEM_PROMPT = """\
あなたは物語の編集者です。
出来事の種を「新しい種」と「棚卸し済みの種」に分けて番号つきで渡すので、同じ出来事を言い換えただけの種の組を見つけ、一つにまとめてください。
- 立場・きっかけ・展開・結末がほぼ同じものだけをまとめる。題材が近いだけで展開の違うものはまとめない。
- 組には新しい種を一つ以上含める。棚卸し済みの種どうしは、既に見比べてあるのでまとめない。
- まとめた種は一〜二文。まとめる種の要素を落とさず、人名・地名・年代は入れない。
- まとめる組が無ければ merges は空のリストにする。
JSON で答えてください。キーは merges(各要素は numbers(まとめる種の番号のリスト)と text(まとめた種)の二つ)だけ。"""

_CONSOLIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "merges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "numbers": {"type": "array", "items": {"type": "integer"}},
                    "text": {"type": "string"},
                },
                "required": ["numbers", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["merges"],
    "additionalProperties": False,
}

_PLOT_SECTION = re.compile(r"^#[ \t]*plot[ \t]*\n(.*?)(?=^#[ \t]|\Z)", re.M | re.S)


_SCHEMA = {
    "type": "object",
    "properties": {"seeds": {"type": "array", "items": {"type": "string"}}},
    "required": ["seeds"],
    "additionalProperties": False,
}


def _plot_section(text: str | None) -> str:
    match = _PLOT_SECTION.search(text or "")
    return match.group(1).strip() if match else ""


# 元のテーブルと、そこから種を抜き出す本文。話は種(`key`)を、無ければ本文を使う。
_SOURCE_TEXTS = (
    (Story, lambda story: story.text),
    (Episode, lambda episode: (episode.key or "").strip() or episode.text),
    (Character, lambda character: _plot_section(character.text)),
    (Event, lambda event: event.text),
)

_Pending = tuple[Story | Episode | Character | Event, str]


def _batches(items: list[tuple[object, str]], limit: int) -> list[list]:
    batches: list[list] = []
    letters = 0
    for item in items:
        if batches and letters + len(item[1]) <= limit:
            batches[-1].append(item)
            letters += len(item[1])
        else:
            batches.append([item])
            letters = len(item[1])
    return batches


def _pending(session: Session) -> list[_Pending]:
    pending = []
    for model, text_of in _SOURCE_TEXTS:
        for record in session.scalars(event_seed_query.unseeded_select(model)).all():
            text = (text_of(record) or "").strip()
            if text:
                pending.append((record, text))
    return pending


def refresh(session: Session, ai: AIClient) -> int:
    pending = _pending(session)
    added = 0
    for batch in _batches(pending, constants.EVENT_SEED_BATCH_LETTERS):
        numbered = "\n\n".join(
            f"## 元{number}({record.__tablename__})\n{text}"
            for number, (record, text) in enumerate(batch, start=1))
        decided = ai.try_generate_json(
            f"{numbered}\n\nそれぞれの元から出来事の種を抜き出してください。",
            _SCHEMA, system=_SYSTEM_PROMPT, timeout=constants.EVENT_SEED_TIMEOUT)
        if "seeds" not in decided:
            print(f"[time_keepr/seed] 元{len(batch)}件から種を抜き出せなかった。次の回に抜き出し直す")
            continue
        for seed in decided["seeds"] or []:
            text = seed.strip() if isinstance(seed, str) else ""
            if text:
                session.add(EventSeed(text=text))
                added += 1
        for record, _ in batch:
            record.event_seeded = True
        session.commit()
    if pending:
        print(f"[time_keepr/seed] 元{len(pending)}件から抜き出し、種を{added}件足した")
    return added


def _merge(session: Session, fresh: list[EventSeed], settled: list[EventSeed], ai: AIClient) -> list[EventSeed] | None:
    numbered = [*fresh, *settled]
    lines = ["## 新しい種", *(f"{i}. {seed.text}" for i, seed in enumerate(fresh, start=1)),
             "", "## 棚卸し済みの種",
             *(f"{i}. {seed.text}" for i, seed in enumerate(settled, start=len(fresh) + 1))]
    decided = ai.try_generate_json(
        "\n".join(lines) + "\n\n同じ出来事を言い換えただけの種の組をまとめてください。",
        _CONSOLIDATE_SCHEMA, system=_CONSOLIDATE_SYSTEM_PROMPT, timeout=constants.EVENT_SEED_TIMEOUT)
    if "merges" not in decided:
        return None
    merged: set[int] = set()
    for merge in decided["merges"] or []:
        if not isinstance(merge, dict):
            continue
        text = (merge.get("text") or "").strip()
        try:
            numbers = {int(number) for number in merge.get("numbers") or []}
        except (TypeError, ValueError):
            continue
        valid = (text and len(numbers) >= 2 and not numbers & merged
                 and all(1 <= number <= len(numbered) for number in numbers)
                 and any(number <= len(fresh) for number in numbers))
        if not valid:
            continue
        for number in numbers:
            session.delete(numbered[number - 1])
        session.add(EventSeed(text=text, consolidated=True))
        merged |= numbers
        print(f"[time_keepr/seed] 種{len(numbers)}件をまとめた: {text}")
    session.commit()
    return [seed for i, seed in enumerate(fresh, start=1) if i not in merged]


def consolidate(session: Session, ai: AIClient) -> int:
    fresh = list(session.scalars(
        select(EventSeed).where(EventSeed.consolidated.is_(False)).order_by(EventSeed.id)).all())
    if len(fresh) < constants.EVENT_SEED_CONSOLIDATE_EVERY:
        return 0
    before = session.query(EventSeed).count()
    settled = list(session.scalars(
        select(EventSeed).where(EventSeed.consolidated.is_(True)).order_by(EventSeed.id)).all())
    chunks = _batches([(seed, seed.text) for seed in settled], constants.EVENT_SEED_CONSOLIDATE_LETTERS) or [[]]
    for chunk in chunks:
        fresh = _merge(session, fresh, [seed for seed, _ in chunk], ai)
        if fresh is None:
            print("[time_keepr/seed] 棚卸しの答えが得られなかった。次の回にやり直す")
            return before - session.query(EventSeed).count()
    for seed in fresh:
        seed.consolidated = True
    session.commit()
    removed = before - session.query(EventSeed).count()
    print(f"[time_keepr/seed] 棚卸しで種を{removed}件減らした(残り{before - removed}件)")
    return removed


def draw(session: Session, rng: random.Random, count: int = constants.EVENT_SEED_DRAW_COUNT) -> list[str]:
    seeds = session.scalars(select(EventSeed.text).order_by(EventSeed.id)).all()
    return rng.sample(list(seeds), min(count, len(seeds)))
