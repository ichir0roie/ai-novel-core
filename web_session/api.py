#!/usr/bin/env python3
"""web のセッションから Lambda の API(`novel-api`)を呼ぶ。

web のセッションは db に繋がず AWS の鍵も持たない。関数 URL は AWS の署名が無いと通らないので、画面(Amplify)の `/api/*` を
web 用の合言葉付きの HTTPS で叩き、Amplify が合言葉を確かめてから署名して関数 URL へ流す。
`NOVEL_API_URL`(Amplify の URL)と `NOVEL_API_KEY`(web 用の合言葉)は、web の環境の環境変数に置く(`.docs/web-session.md`)。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import cast

from pydantic import BaseModel, TypeAdapter

from data_access_logic.step import output_type, step_id
from web_session.transport import ApiError, post, run_entrance

__all__ = ["ApiError", "call", "run_entrance"]


def call[Out](step: Callable[..., Out], form: BaseModel | None = None) -> Out:
    """db の段(`data_access_logic/<領域>/steps.py`)を API で回し、出力の型注釈のモデルで受ける。

    入力は渡した欄だけを送る(修正のフォームは、渡した欄だけを直す。省いた欄は API の側で同じ既定値になる)。"""
    body = None if form is None else form.model_dump(mode="json", exclude_unset=True)
    return cast(Out, TypeAdapter(output_type(step)).validate_python(post(f"/api/steps/{step_id(step)}", body)))

