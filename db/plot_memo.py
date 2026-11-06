#!/usr/bin/env python3
"""話のプロット(`episode.plot_text`)のうち、画面のほかの書き手が書いてよい所。

プロットは作者が画面で組み立てる。AI に具体的な文を書かせると、作者の考えがそれに寄ってしまうため。
画面のほかの書き手(手元の Claude・web のセッション・AI の流れ)は、プロットの末尾のメモの節に、短い箇条書きを足すことだけができる。
守り(`db/guard.py`)が、話の行を足す・直すたびにここで確かめる。
"""
from __future__ import annotations

# 画面のほかの書き手が箇条書きを足してよい節の見出し。「## 推敲」はスキル `revise-episode` が直す指示を控える節
MEMO_HEADINGS = ("## メモ", "## 推敲")
# 一度に足せる箇条書きの数と、一行の字数(頭の「- 」を除く)の上限。メモ・予定の程度に留め、プロットの文に起こさせない
MAX_MEMO_LINES = 5
MAX_MEMO_CHARS = 120


class PlotMemoError(ValueError):
    pass


def _in_memo(text: str) -> bool:
    """`text` の最後の見出しがメモの節の見出しか(そのあとに足せば、その節に入る)。"""
    headings = [line.strip() for line in text.splitlines() if line.lstrip().startswith("#")]
    return bool(headings) and headings[-1] in MEMO_HEADINGS


def check_appended(old: str, new: str) -> None:
    """`old` から `new` への書き換えが、末尾のメモの節に短い箇条書きを足すことだけかを確かめる。違えば `PlotMemoError`。"""
    base, trimmed = old.rstrip(), new.rstrip()
    if trimmed == base:
        return
    if not trimmed.startswith(base) or (base and not trimmed[len(base):].startswith("\n")):
        raise PlotMemoError(
            "プロットの本文は作者が画面で書く。画面のほかからは、末尾の「## メモ」「## 推敲」の節に短い箇条書きを足すことだけができる")
    in_memo = _in_memo(base)
    added = 0
    for line in (line.strip() for line in trimmed[len(base):].splitlines()):
        if not line:
            continue
        if line in MEMO_HEADINGS:
            in_memo = True
            continue
        if not in_memo or not line.startswith("- "):
            raise PlotMemoError(
                f"プロットに足せるのは「## メモ」「## 推敲」の節の「- 」で始まる箇条書きだけ(足そうとした行: {line[:40]})")
        if len(line) - 2 > MAX_MEMO_CHARS:
            raise PlotMemoError(f"プロットのメモは一行 {MAX_MEMO_CHARS} 字まで(足そうとした行: {line[:40]}…)")
        added += 1
    if added > MAX_MEMO_LINES:
        raise PlotMemoError(f"プロットのメモは一度に {MAX_MEMO_LINES} 行まで(足そうとした行: {added})")
