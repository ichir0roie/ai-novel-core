#!/usr/bin/env python3
"""本文の改行を整える `layout_novel_text`。書き方の文はここに持たず、db の `style_preference` から読む。"""
from __future__ import annotations

import re

_SENTENCE_END = "。！？"
_FULL_WIDTH_MARKS = str.maketrans("?!", "？！")
_COMMA = "、"
_QUOTE_OPEN = "「『"
_QUOTE_CLOSE = "」』"


def _quote_depth(text: str, depth: int = 0) -> int:
    for char in text:
        if char in _QUOTE_OPEN:
            depth += 1
        elif char in _QUOTE_CLOSE:
            depth = max(depth - 1, 0)
    return depth


# 長い行の折り返しは載せる媒体に任せる。前に折り返して入れた行(「」が閉じていない行・読点で終わる行)は、
# 前の行へつなぎ直してから整える。
def _join_wrapped_lines(lines: list[str]) -> list[str]:
    joined, depth = [], 0
    for raw in lines:
        line = raw.strip()
        if joined and (depth > 0 or joined[-1].endswith(_COMMA)):
            # 「？」の後ろの全角の空白で折り返した行は、行頭の全角の空白を残してつなぐ
            joined[-1] += raw.rstrip().lstrip(" \t")
        else:
            joined.append(line)
        depth = _quote_depth(line, depth)
    return joined


def _split_sentences(line: str) -> list[str]:
    sentences, current, depth = [], "", 0
    for index, char in enumerate(line):
        current += char
        if char in _QUOTE_OPEN:
            depth += 1
        elif char in _QUOTE_CLOSE:
            depth = max(depth - 1, 0)
        elif depth == 0 and char in _SENTENCE_END:
            following = line[index + 1:index + 2]
            if following and following in _SENTENCE_END + _QUOTE_CLOSE:
                continue
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())
    return sentences


# 空行一つは話し手や流れの切れ目、空行二つ以上は場面の切れ目として読む。
# 地の文は一文一行にする。半角の「?」「!」は全角にそろえる。
def layout_novel_text(text: str) -> str:
    scenes = []
    text = re.sub(r"(?<=[?!]) +(?=\S)", "", text.replace("\r\n", "\n")).translate(_FULL_WIDTH_MARKS)
    for scene in re.split(r"\n[ \t　]*\n(?:[ \t　]*\n)+", text.strip()):
        if not scene.strip():
            continue
        beats = [beat for beat in re.split(r"\n[ \t　]*\n", scene.strip()) if beat.strip()]
        scenes.append("\n\n".join(
            "\n".join(sentence for line in _join_wrapped_lines(beat.splitlines())
                      for sentence in _split_sentences(line))
            for beat in beats))
    return "\n\n\n".join(scenes)

