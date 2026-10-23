#!/usr/bin/env python3
"""名前の仮置き。名づけの語の響き・表記は db の文体の行(全体の「名づけ」、人物の名の形)に、候補の出し方は名づけの仕事の指示(`data_access_logic/character/naming.py`)に持つ。"""
from __future__ import annotations

import re

# AI に名前そのものを書かせると綴りが name の記録とずれるので、文中ではこの仮置きで指させ、
# 名前が決まってから機械的に置き換える。
NAME_PLACEHOLDER = "【名前】"

# AI は括弧の種類・内側の空白まで指示通りには書かないので、表記ゆれも拾う。
# 括弧の無い「名前」は普通の語としても出るので拾わない。
_NAME_PLACEHOLDER_PATTERN = re.compile(r"[【\[(]\s*名前\s*[】\])]")


def fill_name_placeholder(text: str, name: str) -> str:
    text = _NAME_PLACEHOLDER_PATTERN.sub(name, text)
    if not name:
        return text
    # 渡した名前を知っている AI は、仮置きの中身を名前に書き換えて【名前】の括弧だけ残すことがある
    return re.sub(rf"【\s*{re.escape(name)}\s*】", name, text)
