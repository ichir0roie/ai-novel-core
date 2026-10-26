#!/usr/bin/env python3
"""書き込みの書き手(誰の手で書くか)と、展開(`expansion`)の id を、呼び出しの文脈として持つ。

守り(`db/guard.py`)は書き込むたびにここを読み、足した行の出自を決め、書き手に許されない直し・消しを止める。
web のセッションは段・入口を API で回すので、同じ値をヘッダ(`HEADERS`)で運び、API の側で `writing` に戻す。
"""
from __future__ import annotations

import enum
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace


class Writer(enum.StrEnum):
    # 作者(画面、作者が確かめて確定する Claude のセッション)。どの行も直せる
    USER = "user"
    # 作者モードの展開。出自が ai の行だけを直せる・消せる
    AI = "ai"
    # 人物モード。足すことと、空の `end` に時刻を入れることだけ
    AI_APPEND = "ai_append"


@dataclass(frozen=True)
class Writing:
    writer: Writer = Writer.USER
    # 立っていれば、変えた行を `expansion_change` に記録する
    expansion_id: int | None = None
    # AI が作者の確かめを経ずに生んだ行を書いている(AI の生成の流れ)。足した行の出自を ai にし、作者の行に書いても出自を変えない
    generated: bool = False

    @property
    def by_ai(self) -> bool:
        return self.writer is not Writer.USER


_writing: ContextVar[Writing] = ContextVar("writing", default=Writing())

WRITER_HEADER = "x-novel-writer"
EXPANSION_HEADER = "x-novel-expansion"
GENERATED_HEADER = "x-novel-generated"


def current() -> Writing:
    return _writing.get()


@contextmanager
def writing(writer: Writer | str, expansion_id: int | None = None) -> Iterator[Writing]:
    """書き手を立てる。`generated` は外の文脈のものを引き継ぐ。"""
    state = replace(current(), writer=Writer(writer), expansion_id=expansion_id)
    token = _writing.set(state)
    try:
        yield state
    finally:
        _writing.reset(token)


@contextmanager
def generated() -> Iterator[Writing]:
    """AI の生成の流れの中で書く。書き手は外の文脈のまま。"""
    state = replace(current(), generated=True)
    token = _writing.set(state)
    try:
        yield state
    finally:
        _writing.reset(token)


@contextmanager
def restored(state: Writing) -> Iterator[Writing]:
    token = _writing.set(state)
    try:
        yield state
    finally:
        _writing.reset(token)


def headers(state: Writing | None = None) -> dict[str, str]:
    """API に運ぶヘッダ。既定の値は送らない。"""
    state = state or current()
    sent = {}
    if state.writer is not Writer.USER:
        sent[WRITER_HEADER] = state.writer.value
    if state.expansion_id is not None:
        sent[EXPANSION_HEADER] = str(state.expansion_id)
    if state.generated:
        sent[GENERATED_HEADER] = "1"
    return sent


def from_headers(given: Mapping[str, str], fixed_user: bool = False) -> Writing:
    """API が受けたヘッダから書き手を戻す。`fixed_user`(画面の鍵)なら、ヘッダに関わらず作者にする。"""
    if fixed_user:
        return Writing()
    expansion = given.get(EXPANSION_HEADER)
    return Writing(writer=Writer(given.get(WRITER_HEADER) or Writer.USER),
                   expansion_id=int(expansion) if expansion else None,
                   generated=given.get(GENERATED_HEADER) == "1")
