#!/usr/bin/env python3
"""名前の仮置き。名づけの語の響き・表記は db の文体の行(全体の「名づけ」、人物の名の形)に、候補の出し方は名づけの仕事の指示(`data_access_logic/character/naming.py`)に持つ。"""
from __future__ import annotations

import re

# 名前をまだ決めていない・確定済みの名前を AI に書き写させたくない場面で、
# 本文中でその一件を指すのに使う仮置き。名前が決まった後、この文字列を
# 確定した name へ機械的に置き換える(AI に名前そのものを書かせて、綴りが
# name の記録とずれるのを避けるため)。
NAME_PLACEHOLDER = "【名前】"

# AI は括弧の種類・内側の空白まで指示通りに再現するとは限らないため、
# 「名前」を囲む括弧の表記ゆれ(全角/半角、前後の空白)は許容して拾う。
# 括弧の無い裸の「名前」は普通の日本語としても出現しうるので対象にしない。
_NAME_PLACEHOLDER_PATTERN = re.compile(r"[【\[(]\s*名前\s*[】\])]")


def fill_name_placeholder(text: str, name: str) -> str:
    text = _NAME_PLACEHOLDER_PATTERN.sub(name, text)
    if not name:
        return text
    # 渡した名前を知っている AI は、仮置きの中身を名前に書き換えて【名前】の括弧だけ残すことがある
    return re.sub(rf"【\s*{re.escape(name)}\s*】", name, text)
