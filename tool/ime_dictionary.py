#!/usr/bin/env python3
"""作品の語句(人物・名字・アイデア・作中の呼び名・場所・作品の名前)を db から集め、Google 日本語入力の辞書を書き出す。

語句は作品の中身なので、書き出し先はリポジトリの外のディレクトリにする。そこに二つのファイルを置く。

    readings.tsv     単語<TAB>読み<TAB>出どころ。読みの元。カナだけの語は読みを自動で埋め、
                     漢字などを含む語は読みを空のまま足す(手で埋める)。読みを `-` にした語は辞書に入れない
    google_ime.txt   Google 日本語入力の「辞書ツール → 管理 → 新規辞書にインポート」に渡すファイル

回すたびに readings.tsv を今の db の語句で作り直す(埋めた読みは引き継ぎ、db から消えた語は落とす)。

    .venv/bin/python -m tool.ime_dictionary ~/ime-dictionary
"""
from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from data_access_logic.logs import configure_logging
from db.schema import CHARACTER_KIND_PERSON, Character, CharacterParameter, Idea, IdeaHistory, Location, Story, get_env_session

logger = logging.getLogger(__name__)

READINGS_FILE = "readings.tsv"
DICTIONARY_FILE = "google_ime.txt"
EXCLUDED = "-"

# 読みに持てない区切り(名前の中の「・」や空白)は読みから落とす
_SEPARATORS = re.compile(r"[・\s]")
_KANA = re.compile(r"[ぁ-ゖァ-ヶー]+")


@dataclass
class Term:
    word: str
    part_of_speech: str
    source: str


def collect_terms() -> list[Term]:
    """db の語句を、同じ語は最初の出どころだけにして返す。"""
    terms: list[Term] = []
    with get_env_session() as s:
        for character in s.scalars(select(Character).order_by(Character.id)):
            if character.name:
                part = "人名" if character.kind == CHARACTER_KIND_PERSON else "固有名詞"
                terms.append(Term(character.name, part, f"人物・対象:{character.kind}"))
        for family_name in s.scalars(
                select(CharacterParameter.family_name).where(CharacterParameter.family_name.is_not(None))
                .distinct().order_by(CharacterParameter.family_name)):
            terms.append(Term(family_name, "姓", "名字"))
        for idea in s.scalars(select(Idea).order_by(Idea.id)):
            # 「施設」「制度」のような、種別の名前をそのまま付けた行は語句ではない(呼び名も同じ)
            if idea.name and idea.name != idea.kind:
                terms.append(Term(idea.name, "名詞", f"アイデア:{idea.kind}"))
        for name in s.scalars(
                select(IdeaHistory.name).join(Idea, IdeaHistory.idea_id == Idea.id).where(IdeaHistory.name != Idea.kind)
                .distinct().order_by(IdeaHistory.name)):
            terms.append(Term(name, "名詞", "作中の呼び名"))
        for location in s.scalars(select(Location).order_by(Location.id)):
            if location.name:
                terms.append(Term(location.name, "地名", f"場所:{location.kind}"))
        for story in s.scalars(select(Story).order_by(Story.id)):
            terms.append(Term(story.name, "固有名詞", "作品"))
    unique: dict[str, Term] = {}
    for term in terms:
        word = term.word.strip()
        if word and word not in unique:
            unique[word] = Term(word, term.part_of_speech, term.source)
    return list(unique.values())


def kana_reading(word: str) -> str | None:
    """カナだけの語なら、ひらがなの読みを返す。漢字・英字などを含めば None。"""
    reading = _SEPARATORS.sub("", word)
    if not _KANA.fullmatch(reading):
        return None
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in reading)


def read_readings(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    rows = [line.split("\t") for line in path.read_text(encoding="utf-8").splitlines()]
    return {row[0]: row[1].strip() for row in rows if len(row) >= 2 and row[1].strip()}


def write_rows(path: Path, rows: list[list[str]]) -> None:
    path.write_text("".join("\t".join(row) + "\n" for row in rows), encoding="utf-8")


def build(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    known = read_readings(directory / READINGS_FILE)
    terms = collect_terms()

    readings: list[tuple[Term, str]] = []
    for term in terms:
        readings.append((term, known.get(term.word) or kana_reading(term.word) or ""))
    write_rows(directory / READINGS_FILE, [[term.word, reading, term.source] for term, reading in readings])

    entries = [(term, reading) for term, reading in readings if reading and reading != EXCLUDED]
    write_rows(directory / DICTIONARY_FILE,
               [[reading, term.word, term.part_of_speech, term.source] for term, reading in entries])

    unread = [term.word for term, reading in readings if not reading]
    logger.info("語句 %d(辞書 %d・除外 %d・読みが空 %d)を %s に書き出した",
                len(readings), len(entries), sum(reading == EXCLUDED for _, reading in readings), len(unread), directory)
    if unread:
        logger.info("読みが空の語は %s の 2 列目を埋めて回し直す(入れない語は `-`)", READINGS_FILE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", type=Path, help="書き出すディレクトリ(リポジトリの外)")
    configure_logging()
    build(parser.parse_args().directory.expanduser())


if __name__ == "__main__":
    main()
