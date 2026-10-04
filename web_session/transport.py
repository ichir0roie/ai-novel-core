#!/usr/bin/env python3
"""web のセッションから画面(Amplify)の `/api/*` を合言葉付きで叩く。

db の表の定義(sqlalchemy)を読み込まないので、手番を待つコマンド(`tool.episode_session`)のように何度も起こすものが
すぐ立ち上がる。段の型で受けるのは `web_session/api.py`。
"""
from __future__ import annotations

import os
from typing import Any

import httpx

# `gui/api/app.py` の `API_KEY_HEADER` と同じ名前
_API_KEY_HEADER = "x-novel-api-key"
# 段は db だけなので短いが、Lambda の立ち上がり(コンテナの冷えた起動)を待てるようにする
_TIMEOUT = 120.0

# 手番を待つあいだ毎秒呼ぶので、接続を使い回して TLS の握手を一度で済ませる
_client: httpx.Client | None = None


class ApiError(RuntimeError):
    pass


def _base_url() -> str:
    url = os.environ.get("NOVEL_API_URL", "").strip().rstrip("/")
    if not url:
        raise ApiError("NOVEL_API_URL(Amplify の URL)が無い。web の環境の環境変数に置く")
    return url


def post(path: str, body: Any) -> Any:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=_TIMEOUT)
    response = _client.post(f"{_base_url()}{path}", json=body,
                            headers={_API_KEY_HEADER: os.environ.get("NOVEL_API_KEY", "")})
    if response.is_error:
        raise ApiError(f"{path} が {response.status_code} を返した: {response.text[-2000:]}")
    return response.json()


def run_entrance(entrance_id: str, args: dict[str, Any]) -> Any:
    """db だけの入口(`data_access_logic` の入口のうち claude を叩かないもの)を API で呼び、結果の JSON を返す。"""
    return post(f"/api/interface/{entrance_id}", {"args": args})["result"]
