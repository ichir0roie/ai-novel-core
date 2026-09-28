#!/usr/bin/env python3
"""AWS Lambda から gui.api.app:app を呼ぶための入口。Mangum で ASGI をラップするだけ。

Lambda はブラウザから直接ではなく、Amplify Hosting の Next.js(`rewrites`)経由でだけ叩かれる想定。
CLAUDECODE は Lambda の環境に無いので、`claude` を叩く入口は `gui.api.claude_env.require_claude_code` が
そのまま 403 で止める(ローカル・Claude Code セッション限定の機能は、コードを分けずにここで自然に塞がる)。

Lambda 関数のハンドラには `gui.api.lambda_handler.handler` を指定する。
"""
from __future__ import annotations

from mangum import Mangum

from gui.api.app import app

handler = Mangum(app)
