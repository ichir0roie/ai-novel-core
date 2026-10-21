#!/usr/bin/env python3
"""本文の改行を整える `layout_novel_text`。

書き方の文(文体・作風・注意書き・行の組み方)はここに定数で持たず、db の `style_preference` から読む
(`data_access_logic/style_preference/extras.py`。初期値は `db/style_defaults.py`)。
"""
from __future__ import annotations

import re

# 一行がこの字数を超えるときは、文の切れ目か読点で折り返す。
LINE_LETTERS = 50

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


# 折り返した行(「」が閉じていない行・読点で終わる行)は、前の行へつなぎ直してから整える。
def _join_wrapped_lines(lines: list[str]) -> list[str]:
    joined, depth = [], 0
    for line in (line.strip() for line in lines):
        if joined and (depth > 0 or joined[-1].endswith(_COMMA)):
            joined[-1] += line
        else:
            joined.append(line)
        depth = _quote_depth(line, depth)
    return joined


def _cut_after(text: str, marks: str) -> list[str]:
    pieces, current = [], ""
    for index, char in enumerate(text):
        current += char
        following = text[index + 1:index + 2]
        if char in marks and following and following not in marks + _QUOTE_CLOSE:
            pieces.append(current)
            current = ""
    if current:
        pieces.append(current)
    return pieces


def _wrap(sentence: str) -> list[str]:
    if len(sentence) <= LINE_LETTERS:
        return [sentence]
    pieces = [part for piece in _cut_after(sentence, _SENTENCE_END)
              for part in (_cut_after(piece, _COMMA) if len(piece) > LINE_LETTERS else [piece])]
    lines = [""]
    for piece in pieces:
        if lines[-1] and len(lines[-1]) + len(piece) > LINE_LETTERS:
            lines.append(piece)
        else:
            lines[-1] += piece
    return lines


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
# 読点も文の切れ目も無い長い文は、折り返さずに残す。半角の「?」「!」は全角にそろえる。
def layout_novel_text(text: str) -> str:
    scenes = []
    text = re.sub(r"(?<=[?!]) +(?=\S)", "", text.replace("\r\n", "\n")).translate(_FULL_WIDTH_MARKS)
    for scene in re.split(r"\n[ \t　]*\n(?:[ \t　]*\n)+", text.strip()):
        if not scene.strip():
            continue
        beats = [beat for beat in re.split(r"\n[ \t　]*\n", scene.strip()) if beat.strip()]
        scenes.append("\n\n".join(
            "\n".join(wrapped for line in _join_wrapped_lines(beat.splitlines())
                      for sentence in _split_sentences(line) for wrapped in _wrap(sentence))
            for beat in beats))
    return "\n\n\n".join(scenes)

