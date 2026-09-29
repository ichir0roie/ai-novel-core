#!/usr/bin/env python3
from __future__ import annotations

import logging


def configure_logging() -> None:
    """途中経過(info)から標準エラーに出す。標準出力は `show()` などの結果だけにする。

    呼ぶ側がもう設定していれば何もしない(`logging.basicConfig` の決まり)。
    """
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
