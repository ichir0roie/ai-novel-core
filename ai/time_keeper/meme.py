#!/usr/bin/env python3
"""ミームどうし・元との関係は持たない(移り変わり・伝染していくため)。"""
from __future__ import annotations

import random
import re

from sqlalchemy import select

from ai.instructions.sensitive import BIO_ABSTRACTION_INSTRUCTION
from ai.time_keeper import constants
from ai.time_keeper._ai import AIClient
from data_access_logic.query import meme_query
from db.schema import MEME_CATEGORIES, Character, ConfirmStatus, Event, Idea, Meme, Oracle, Session

CATEGORY_DESCRIPTIONS = {
    "信条": "何を大事にし、どう振る舞うか。一人の行動の型",
    "欲求": "何を求めて動くか",
    "境遇": "特定の状況に置かれたときの葛藤・選択",
    "集団": "国・組織・集団として働く論理",
    "理": "世界の法則や代償。誰かが持つ考え方ではない",
}

_CATEGORY_GUIDE = "\n".join(f"  - {name}: {CATEGORY_DESCRIPTIONS[name]}" for name in MEME_CATEGORIES)

_SYSTEM_PROMPT = f"""\
あなたは物語の編集者です。
用語の説明・著者の創作についての覚え書き・それらの検証結果・人物の筋書き・起きた出来事をいくつか番号つきで渡すので、それぞれから、\
人物の行動原理の芯になりうる「ミーム」(繰り返し現れる考え方・価値観・行動の型)を抜き出してください。
- 人名・地名・組織名・その作品だけの固有名詞を抜き、他の人物にも乗り移りうる普遍的な考え方として書く。
- 一つのミームは一文。何を大事にし、何を避け、何をきっかけに動くかが分かるように書く。
- 固有名詞を抜いても特定の人物の役どころ・筋書き上の境遇をなぞるだけのもの(その人物にしか当てはまらない立場や状況)は抜き出さない。引いた人物がその人物の写しになるため。
- 作者の前書き・使用環境・書き方の約束など、考え方にならない文からは抜き出さない。
- 出来事(event)からは、当事者がその出来事を経て選んだこと・手放したこと・行き着いた考え方だけを抜き出す。起きたことをなぞっただけの記録からは抜き出さない。
- 本文中の「検証結果」の節は、用語の説明や覚え書きを現実の科学・歴史・思想・心理学に照らした調べ書き。\
そこに出てくる現実の人・集団の考え方や、研究で裏付けられた行動の傾向を、人物の行動原理になりうる考え方として抜き出す。\
出典の一覧や、妥当性の判定そのものからは抜き出さない。
- 一つの元から 0〜3 件。同じ元の中で似たミームは一つにまとめる。
- それぞれに、次の分類から一つを振る。
{_CATEGORY_GUIDE}
{BIO_ABSTRACTION_INSTRUCTION}
JSON で答えてください。キーは memes だけ。各要素は text(ミームの一文)と category(分類)の二つ。"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "memes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "category": {"type": "string", "enum": list(MEME_CATEGORIES)},
                },
                "required": ["text", "category"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["memes"],
    "additionalProperties": False,
}

_DEDUPE_SYSTEM_PROMPT = """\
あなたは物語の編集者です。
人物の行動原理になる「ミーム」を「新しいミーム」と「既にあるミーム」に分けて渡すので、新しいミームのうち、\
既にあるミームか、それより前の番号の新しいミームと同じ考え方を言い換えただけのものを見つけてください。
- 何を大事にし、何をきっかけに、どう動くかがほぼ同じものだけを重複とする。題材が近いだけで、大事にするものや動き方が違うものは重複にしない。
- 重複が無ければ duplicates は空のリストにする。
JSON で答えてください。キーは duplicates(重複している新しいミームの番号のリスト)だけ。"""

_DEDUPE_SCHEMA = {
    "type": "object",
    "properties": {"duplicates": {"type": "array", "items": {"type": "integer"}}},
    "required": ["duplicates"],
    "additionalProperties": False,
}

_CLASSIFY_SYSTEM_PROMPT = f"""\
あなたは物語の編集者です。
人物の行動原理になる「ミーム」を番号つきで渡すので、それぞれに次の分類から一つを振ってください。
{_CATEGORY_GUIDE}
JSON で答えてください。キーは categories だけ。各要素は number(ミームの番号)と category(分類)の二つ。"""

_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "category": {"type": "string", "enum": list(MEME_CATEGORIES)},
                },
                "required": ["number", "category"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["categories"],
    "additionalProperties": False,
}

_PLOT_SECTION = re.compile(r"^#[ \t]*plot[ \t]*\n(.*?)(?=^#[ \t]|\Z)", re.M | re.S)


def _plot_section(text: str | None) -> str:
    match = _PLOT_SECTION.search(text or "")
    return match.group(1).strip() if match else ""


# 元のテーブルと、そこから抜き出す (見出し, 本文)。人物は `# plot` の節だけを使う。
# アイデア・oracle の本文には検証結果(`# 検証結果` の節)も含む。
_SOURCE_TEXTS = (
    (Idea, lambda idea: [("idea", idea.text)]),
    (Oracle, lambda oracle: [("oracle", oracle.text)]),
    (Character, lambda character: [("character", _plot_section(character.text))]),
    (Event, lambda event: [("event", event.text)]),
)

# (元のレコード, 本文, 見出し)。一つのレコードから複数の元が出ることがある。
_Pending = tuple[Idea | Oracle | Character | Event, str, str]
# 抜き出したミームの (文面, 分類)。分類が分からなければ None にして、`_classify` に回す。
_Candidate = tuple[str, str | None]


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
    for model, texts_of in _SOURCE_TEXTS:
        for record in session.scalars(meme_query.unseeded_select(model)).all():
            for label, text in texts_of(record):
                text = (text or "").strip()
                if text:
                    pending.append((record, text, label))
    return pending


def _candidates(memes) -> list[_Candidate]:
    candidates = []
    for meme in memes or []:
        if not isinstance(meme, dict):
            continue
        text = meme.get("text").strip() if isinstance(meme.get("text"), str) else ""
        if text:
            category = meme.get("category")
            candidates.append((text, category if category in MEME_CATEGORIES else None))
    return candidates


def _normalized(text: str) -> str:
    return re.sub(r"[\s。、]", "", text)


def _without_duplicates(session: Session, candidates: list[_Candidate], ai: AIClient) -> list[_Candidate] | None:
    existing = list(session.scalars(select(Meme).order_by(Meme.id)).all())
    seen = {_normalized(meme.text) for meme in existing}
    fresh = []
    for text, category in candidates:
        if _normalized(text) not in seen:
            seen.add(_normalized(text))
            fresh.append((text, category))

    chunks = _batches([(meme, meme.text) for meme in existing], constants.MEME_DEDUPE_LETTERS) or [[]]
    for chunk in chunks:
        if not fresh or (not chunk and len(fresh) < 2):
            break
        lines = ["## 新しいミーム", *(f"{i}. {text}" for i, (text, _) in enumerate(fresh, start=1))]
        if chunk:
            lines += ["", "## 既にあるミーム", *(f"- {meme.text}" for meme, _ in chunk)]
        decided = ai.try_generate_json(
            "\n".join(lines) + "\n\n新しいミームのうち、重複しているものの番号を挙げてください。",
            _DEDUPE_SCHEMA, system=_DEDUPE_SYSTEM_PROMPT, timeout=constants.MEME_TIMEOUT)
        if "duplicates" not in decided:
            return None
        duplicates = set()
        for number in decided["duplicates"] or []:
            try:
                duplicates.add(int(number))
            except (TypeError, ValueError):
                continue
        for number in sorted(duplicates):
            if 1 <= number <= len(fresh):
                print(f"[time_keepr/meme] 既にあるミームと重なるので足さない: {fresh[number - 1][0]}")
        fresh = [item for i, item in enumerate(fresh, start=1) if i not in duplicates]
    return fresh


def _classify(session: Session, ai: AIClient) -> int:
    unclassified = list(session.scalars(
        select(Meme).where(Meme.category.is_(None)).order_by(Meme.id)).all())
    for batch in _batches([(meme, meme.text) for meme in unclassified], constants.MEME_BATCH_LETTERS):
        numbered = "\n".join(f"{i}. {meme.text}" for i, (meme, _) in enumerate(batch, start=1))
        decided = ai.try_generate_json(
            f"{numbered}\n\nそれぞれのミームに分類を振ってください。",
            _CLASSIFY_SCHEMA, system=_CLASSIFY_SYSTEM_PROMPT, timeout=constants.MEME_TIMEOUT)
        for item in decided.get("categories") or []:
            if not isinstance(item, dict):
                continue
            try:
                number = int(item.get("number"))
            except (TypeError, ValueError):
                continue
            if 1 <= number <= len(batch) and item.get("category") in MEME_CATEGORIES:
                meme = batch[number - 1][0]
                meme.category = item["category"]
        session.commit()
    classified = sum(1 for meme in unclassified if meme.category)
    if unclassified:
        print(f"[time_keepr/meme] 分類の空いたミーム{len(unclassified)}件のうち、{classified}件に分類を振った")
    return classified


def _unseed(session: Session, batch: list[_Pending], failed: set) -> None:
    for record, _, _ in batch:
        failed.add(record)
        record.meme_seeded = False
    session.commit()


def refresh(session: Session, ai: AIClient) -> int:
    pending = _pending(session)
    added = 0
    failed: set = set()
    for batch in _batches(pending, constants.MEME_BATCH_LETTERS):
        numbered = "\n\n".join(
            f"## 元{number}({label})\n{text}"
            for number, (_, text, label) in enumerate(batch, start=1))
        decided = ai.try_generate_json(
            f"{numbered}\n\nそれぞれの元からミームを抜き出してください。",
            _SCHEMA, system=_SYSTEM_PROMPT, timeout=constants.MEME_TIMEOUT)
        if "memes" not in decided:
            print(f"[time_keepr/meme] 元{len(batch)}件からミームを抜き出せなかった。次の回に抜き出し直す")
            _unseed(session, batch, failed)
            continue
        fresh = _without_duplicates(session, _candidates(decided["memes"]), ai)
        if fresh is None:
            print(f"[time_keepr/meme] 元{len(batch)}件から抜き出したミームの重複を確かめられなかった。次の回に抜き出し直す")
            _unseed(session, batch, failed)
            continue
        for text, category in fresh:
            session.add(Meme(text=text, category=category))
            added += 1
        for record, _, _ in batch:
            if record not in failed:
                record.meme_seeded = True
        session.commit()
    if pending:
        print(f"[time_keepr/meme] 元{len(pending)}件から抜き出し、ミームを{added}件足した")
    _classify(session, ai)
    return added


def draw(session: Session, rng: random.Random, categories: tuple[str, ...]) -> list[dict]:
    drawn = []
    for category in categories:
        memes = list(session.scalars(
            select(Meme).where(Meme.category == category, Meme.confirmed == ConfirmStatus.APPROVED).order_by(Meme.id)).all())
        count = min(rng.randint(*constants.MEME_DRAW_RANGE), len(memes))
        for meme in rng.sample(memes, count):
            drawn.append({"position": rng.choice(list(constants.MEME_POSITIONS)),
                          "id": meme.id, "category": meme.category, "text": meme.text})
    return drawn


def position_legend() -> str:
    return " / ".join(f"{position}={meaning}" for position, meaning in constants.MEME_POSITIONS.items())


def meme_section(drawn: list[dict]) -> str:
    return "\n".join(f"- {item['position']}: {item['text']}" for item in drawn)
