#!/usr/bin/env python3
"""流れ(`data_access_logic/flows/`)が db の段(`data_access_logic/<領域>/steps.py`)を呼ぶ口。

手元では段を自分のセッションで回し(`step.run`)、web のセッションでは API で回す(`web_session/api.call`)。
流れは `call` だけを使い、どちらで回るかを知らない。web の口に差し替えるのは `web_session/flows.run` が `calling` で行う。
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

from pydantic import BaseModel

from data_access_logic import step


class Caller(Protocol):
    def __call__[Out](self, step: Callable[..., Out], form: BaseModel | None = None) -> Out: ...


_caller: ContextVar[Caller] = ContextVar("caller", default=step.run)


def call[Out](step: Callable[..., Out], form: BaseModel | None = None) -> Out:
    return _caller.get()(step, form)


@contextmanager
def calling(caller: Caller) -> Iterator[None]:
    token = _caller.set(caller)
    try:
        yield
    finally:
        _caller.reset(token)
