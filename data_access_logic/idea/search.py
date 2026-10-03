#!/usr/bin/env python3
"""アイデアのあいまい検索。キーワードとその言い換えで、名前・本文を部分一致で引く。

言い換えは `keywords_of` で AI に作らせるか、呼び出し側(claude)が自分で付けて渡す。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.instructions.sensitive import BIO_ABSTRACTION_INSTRUCTION
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.idea.models import IdeaHit, IdeaDraft, IdeaDraftsByAI, normalized, unique_ideas
from data_access_logic.query import common_query, dictionary_query
from db.schema import Idea
from db.stamp import Stamp

_SYSTEM_PROMPT = f"""\
あなたは物語の設定資料の編集者です。
渡す文から、世界の設定資料(用語集)と照らし合わせるべき語を抜き出し、それぞれに検索用の言い換えを付けてください。
- 抜き出すのは、その世界に固有の、または世界の設定に関わる語: 技術・道具・現象・病や体質・制度・身分・種族・組織の種類・信仰・歴史上の出来事・作中の呼び名など。
- 人名と、固有の場所の名前は抜き出さない。誰にでも通じる日常の語(剣・雨・食事・鍛冶師・交易路など)も、設定上の意味を帯びていなければ抜き出さない。
- 文に語として出ていなくても、文が描いている設定上の事柄(症状の描写なら、その原因になっている体質や病など)があれば、その事柄を指す語を keyword にしてよい。
- variants には、設定資料の側で使われていそうな語を入れる(「虫を宿す治療」なら「寄生」「治療」、「石の病」なら「遺伝」「疾患」のように)。
- start は、文の時刻に初めて現れた事柄ならその時刻、「十年前から」ならそこから数えた年。
{BIO_ABSTRACTION_INSTRUCTION}"""

_NAME_SCORE = 3
_VARIANT_NAME_SCORE = 2
_TEXT_SCORE = 1


def keywords_of(text: str, ai: AIClient, time: Stamp | None = None) -> list[IdeaDraft]:
    """`text` から、アイデアと照らす語とその言い換えを AI に挙げさせる。答えなければ空。

    `time`(文の時刻)を渡すと、それと文の中身から語ごとの `start` / `end` を決めさせる。
    """
    if not (text or "").strip():
        return []
    when = f"この文の時刻: {time}\n\n" if time is not None else ""
    decided = ai.generate(
        f"{when}{text}\n\nこの文から、設定資料と照らし合わせる語を挙げてください。",
        IdeaDraftsByAI, system=_SYSTEM_PROMPT, timeout=constants.IDEA_DRAFTS_TIMEOUT)
    if decided is None:
        return []
    return unique_ideas(list(decided.ideas))


def _kana_swapped(text: str) -> str:
    swapped = []
    for char in text:
        code = ord(char)
        if 0x3041 <= code <= 0x3096:
            swapped.append(chr(code + 0x60))
        elif 0x30A1 <= code <= 0x30F6:
            swapped.append(chr(code - 0x60))
        else:
            swapped.append(char)
    return "".join(swapped)


def spellings(word: str) -> list[str]:
    """ひらがな・カタカナを入れ替えた書き方も含める。"""
    word = normalized(word)
    return list(dict.fromkeys(spelling for spelling in (word, _kana_swapped(word)) if spelling))


def _contains(haystack: str | None, needle: str) -> bool:
    return needle.casefold() in normalized(haystack).casefold()


def _spelled(idea: IdeaDraft) -> tuple[list[str], list[str]]:
    keyword = spellings(idea.keyword)
    variants = [spelling for variant in idea.variants for spelling in spellings(variant) if spelling not in keyword]
    return keyword, list(dict.fromkeys(variants))


def _score(idea: Idea, keyword: list[str], variants: list[str]) -> int:
    # 場所・時代を問わず、作中の呼び名(idea_history)にも本質と同じ強さで当たる
    names = [idea.name, *(history.name for history in idea.histories)]
    if any(_contains(name, spelling) for name in names for spelling in keyword):
        return _NAME_SCORE
    if any(_contains(name, spelling) for name in names for spelling in variants):
        return _VARIANT_NAME_SCORE
    texts = [idea.text, *(history.detail or "" for history in idea.histories)]
    if any(_contains(text, spelling) for text in texts for spelling in keyword + variants):
        return _TEXT_SCORE
    return 0


def search(
    s: Session, keywords: list[IdeaDraft], location_id: int | None = None, time: Stamp | None = None,
    limit: int | None = None,
) -> list[IdeaHit]:
    """キーワードと言い換えで引いたアイデアを、当たり方の強い順に返す。

    名前にキーワードが入っていれば 3、言い換えが入っていれば 2、本文にだけ入っていれば 1 を、キーワードごとに足す。
    `location_id` / `time` を渡すと、その場所・時刻で効くアイデアに絞る。
    """
    location_ids = common_query.idea_scope_ids(s, location_id) if location_id is not None else None
    scores: dict[int, tuple[Idea, int, list[str]]] = {}
    for idea_draft in unique_ideas(keywords):
        keyword, variants = _spelled(idea_draft)
        for idea in s.scalars(dictionary_query.ideas_by_keywords_select(
                keyword + variants, location_ids, time)).all():
            score = _score(idea, keyword, variants)
            if not score:
                continue
            _, total, matched = scores.get(idea.id, (idea, 0, []))
            scores[idea.id] = (idea, total + score, [*matched, idea_draft.keyword])
    ranked = sorted(scores.values(), key=lambda found: (-found[1], found[0].id))
    hits = [IdeaHit(idea=idea, score=score, keywords=matched) for idea, score, matched in ranked]
    return hits[:limit] if limit is not None else hits
