#!/usr/bin/env python3
"""web のセッションから Lambda の API(`novel-api`)を呼ぶ。

web のセッションは db に繋がず AWS の鍵も持たない。関数 URL は AWS の署名が無いと通らないので、画面(Amplify)の `/api/*` を
web 用の合言葉付きの HTTPS で叩き、Amplify が合言葉を確かめてから署名して関数 URL へ流す。
`NOVEL_API_URL`(Amplify の URL)と `NOVEL_API_KEY`(web 用の合言葉)は、web の環境の環境変数に置く(`.docs/web-session.md`)。
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, cast

import httpx
from pydantic import BaseModel, TypeAdapter

from data_access_logic.step import output_type, step_id

# `gui/api/app.py` の `API_KEY_HEADER` と同じ名前
_API_KEY_HEADER = "x-novel-api-key"
# 段は db だけなので短いが、Lambda の立ち上がり(コンテナの冷えた起動)を待てるようにする
_TIMEOUT = 120.0


class ApiError(RuntimeError):
    pass


def _base_url() -> str:
    url = os.environ.get("NOVEL_API_URL", "").strip().rstrip("/")
    if not url:
        raise ApiError("NOVEL_API_URL(Amplify の URL)が無い。web の環境の環境変数に置く")
    return url


def _post(path: str, body: Any) -> Any:
    response = httpx.post(f"{_base_url()}{path}", json=body, timeout=_TIMEOUT,
                          headers={_API_KEY_HEADER: os.environ.get("NOVEL_API_KEY", "")})
    if response.is_error:
        raise ApiError(f"{path} が {response.status_code} を返した: {response.text[-2000:]}")
    return response.json()


def call[Out](step: Callable[..., Out], form: BaseModel | None = None) -> Out:
    """db の段(`data_access_logic/<領域>/steps.py`)を API で回し、出力の型注釈のモデルで受ける。

    入力は渡した欄だけを送る(修正のフォームは、渡した欄だけを直す。省いた欄は API の側で同じ既定値になる)。"""
    body = None if form is None else form.model_dump(mode="json", exclude_unset=True)
    return cast(Out, TypeAdapter(output_type(step)).validate_python(_post(f"/api/steps/{step_id(step)}", body)))


def run_entrance(entrance_id: str, args: dict[str, Any]) -> Any:
    """db だけの入口(`data_access_logic` の入口のうち claude を叩かないもの)を API で呼び、結果の JSON を返す。"""
    return _post(f"/api/interface/{entrance_id}", {"args": args})["result"]
