#!/usr/bin/env python3
"""アイデアのあいまい検索。キーワードとその言い換えで、名前・本文を部分一致で引く。

言い換えは `keywords_of` で AI に作らせるか、呼び出し側(claude)が自分で付けて渡す。
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from ai.instructions.sensitive import BIO_ABSTRACTION_INSTRUCTION
from ai.time_keeper import constants
from ai.time_keeper._ai import AIClient
from data_access_logic.query import common_query, dictionary_query
from db.schema import Idea, Session
from db.stamp import Stamp, StampError

_SYSTEM_PROMPT = f"""\
あなたは物語の設定資料の編集者です。
渡す文から、世界の設定資料(用語集)と照らし合わせるべき語を抜き出し、それぞれに検索用の言い換えを付けてください。
- 抜き出すのは、その世界に固有の、または世界の設定に関わる語: 技術・道具・現象・病や体質・制度・身分・種族・組織の種類・信仰・歴史上の出来事・作中の呼び名など。
- 人名と、固有の場所の名前は抜き出さない。誰にでも通じる日常の語(剣・雨・食事・鍛冶師・交易路など)も、設定上の意味を帯びていなければ抜き出さない。
- 文に語として出ていなくても、文が描いている設定上の事柄(症状の描写なら、その原因になっている体質や病など)があれば、その事柄を指す語を keyword にしてよい。
- variants は keyword の表記揺れ・同義語・上位語・作中の人が使いそうな呼び方を 2〜6 個。部分一致で検索するので、keyword を組み立てている 2〜3 字の核の語を必ず含める(「虫を宿す治療」なら「寄生」「治療」、「石の病」なら「遺伝」「疾患」のように、設定資料の側で使われていそうな語)。1 字の語は使わない。
- description は、この文の中でその語が何を指しているかの一文。
- coined は、その語がこの世界・作品に固有の語(作中の呼び名・造語・固有の技術や制度の名)なら true、一般の語なら false。
- kind は、その語の種別を「技術」「制度」「概念」「呼称」「現象」「施設」「時代」などの短い語で一つ。
- start は、その事柄がこの世界に現れた(作られた・始まった・そう呼ばれ始めた)時期。文の時刻と文の中身から、ある程度はっきり言えるときだけ「年」か「年/月/日」で書く(文の時刻に初めて現れた事柄ならその時刻、「十年前から」ならそこから数えた年)。はっきり言えなければ null。
- end は、その事柄が終わった・廃れた・そう呼ばれなくなった時期。文から分かるときだけ start と同じ形で書き、分からなければ null。
- 0〜8 件。
{BIO_ABSTRACTION_INSTRUCTION}
JSON で答えてください。キーは terms だけ。各要素は keyword・variants・description・coined・kind・start・end の七つ。"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "variants": {"type": "array", "items": {"type": "string"}},
                    "description": {"type": "string"},
                    "coined": {"type": "boolean"},
                    "kind": {"type": "string"},
                    "start": {"type": ["string", "null"]},
                    "end": {"type": ["string", "null"]},
                },
                "required": ["keyword", "variants", "description", "coined", "kind", "start", "end"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["terms"],
    "additionalProperties": False,
}

# kind を付けずに渡された語を、自動で足すときの種別
DEFAULT_KIND = "概念"
# 一字の言い換えは、ほかの語の一部(「官」と「器官」など)に当たりすぎる。
_MIN_VARIANT_LETTERS = 2
_NAME_SCORE = 3
_VARIANT_NAME_SCORE = 2
_TEXT_SCORE = 1


@dataclass
class Hit:
    idea: Idea
    score: int = 0
    keywords: list[str] = field(default_factory=list)


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


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
    word = _normalized(word)
    found = []
    for spelling in (word, _kana_swapped(word)):
        if spelling and spelling not in found:
            found.append(spelling)
    return found


def _stamp(value) -> Stamp | None:
    try:
        return Stamp.parse(value)
    except (StampError, TypeError):
        return None


def terms_of(keywords) -> list[dict]:
    """`"語"` / `{"keyword", "variants", "description", "coined", "kind", "start", "end"}` / それらのリストを、そろえた辞書のリストにする。

    `coined` が無ければ true(claude が自分で選んで渡した語は、固有の語として扱う)。`kind` が無ければ `DEFAULT_KIND`。
    `start` / `end` は読めなければ None。`end` が `start` より後でなければ `end` を捨てる。
    """
    if isinstance(keywords, (str, dict)):
        keywords = [keywords]
    terms = []
    seen = set()
    for item in keywords or []:
        if isinstance(item, str):
            item = {"keyword": item}
        if not isinstance(item, dict):
            continue
        keyword = _normalized(item.get("keyword") if isinstance(item.get("keyword"), str) else "")
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        variants = [_normalized(v) for v in item.get("variants") or [] if isinstance(v, str)]
        description = item.get("description") if isinstance(item.get("description"), str) else ""
        kind = _normalized(item.get("kind") if isinstance(item.get("kind"), str) else "")
        start, end = _stamp(item.get("start")), _stamp(item.get("end"))
        if start is not None and end is not None and end <= start:
            end = None
        terms.append({"keyword": keyword,
                      "variants": [v for v in dict.fromkeys(variants)
                                   if len(v) >= _MIN_VARIANT_LETTERS and v != keyword],
                      "description": description.strip(),
                      "coined": item.get("coined", True) is not False,
                      "kind": kind or DEFAULT_KIND,
                      "start": start,
                      "end": end})
    return terms


def keywords_of(text: str, ai: AIClient, time=None) -> list[dict]:
    """`text` から、アイデアと照らす語とその言い換えを AI に挙げさせる。答えなければ空。

    `time`(文の時刻)を渡すと、それと文の中身から語ごとの `start` / `end` を決めさせる。
    """
    if not (text or "").strip():
        return []
    time = Stamp.parse(time)
    when = f"この文の時刻: {time}\n\n" if time is not None else ""
    decided = ai.try_generate_json(
        f"{when}{text}\n\nこの文から、設定資料と照らし合わせる語を挙げてください。",
        _SCHEMA, system=_SYSTEM_PROMPT, timeout=constants.IDEA_TERMS_TIMEOUT)
    return terms_of(decided.get("terms") or [])


def _contains(haystack: str | None, needle: str) -> bool:
    return needle.casefold() in _normalized(haystack or "").casefold()


def _spelled(term: dict) -> tuple[list[str], list[str]]:
    keyword = spellings(term["keyword"])
    variants = [s for v in term["variants"] for s in spellings(v) if s not in keyword]
    return keyword, list(dict.fromkeys(variants))


def _score(idea: Idea, keyword: list[str], variants: list[str]) -> int:
    if any(_contains(idea.name, s) for s in keyword):
        return _NAME_SCORE
    if any(_contains(idea.name, s) for s in variants):
        return _VARIANT_NAME_SCORE
    if any(_contains(idea.text, s) for s in keyword + variants):
        return _TEXT_SCORE
    return 0


def search_by_term(
    session: Session, keywords, place_id: int | None = None, time=None,
    confirmed_only: bool = True,
) -> list[tuple[dict, list[Idea]]]:
    """キーワードごとに当たったアイデア。`place_id` / `time` を渡すと、その場所・時刻で効くアイデアに絞る。

    `confirmed_only` を false にすると、まだ確かめていない候補(`confirmed=false`)も含める。"""
    place_ids = common_query.idea_scope_ids(session, place_id) if place_id is not None else None
    time = Stamp.parse(time)
    found = []
    for term in terms_of(keywords):
        keyword, variants = _spelled(term)
        rows = session.scalars(dictionary_query.ideas_by_terms_select(
            keyword + variants, place_ids, time, confirmed_only=confirmed_only)).all()
        found.append((term, [idea for idea in rows if _score(idea, keyword, variants)]))
    return found


def search(
    session: Session, keywords, place_id: int | None = None,
    time=None, limit: int | None = None, confirmed_only: bool = True,
) -> list[Hit]:
    """キーワードと言い換えで引いたアイデアを、当たり方の強い順に返す。

    名前にキーワードが入っていれば 3、言い換えが入っていれば 2、本文にだけ入っていれば 1 を、キーワードごとに足す。
    `confirmed_only` を false にすると、まだ確かめていない候補(`confirmed=false`)も含める。
    """
    hits: dict[int, Hit] = {}
    for term, ideas in search_by_term(session, keywords, place_id, time, confirmed_only=confirmed_only):
        keyword, variants = _spelled(term)
        for idea in ideas:
            hit = hits.setdefault(idea.id, Hit(idea))
            hit.score += _score(idea, keyword, variants)
            hit.keywords.append(term["keyword"])
    ranked = sorted(hits.values(), key=lambda hit: (-hit.score, hit.idea.id))
    return ranked[:limit] if limit is not None else ranked
