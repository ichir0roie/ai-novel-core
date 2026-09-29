#!/usr/bin/env python3
"""土台(`*_BASE`)はここに定数で置く、共通・対象ごとの固定の文体指示。

世界の舞台設定や、既存の話(`Episode`)の本文から抽出した文体の癖のような、世界ごとに違う
「好み」は、ここには定数で持たない。`style_instruction()` の `shared_extra`(共通に効く)・
`extra`(その対象だけに効く)として、呼び出し側(親リポジトリ側)から渡す。

対象ごとの土台は共通とは別に持っているので、あとから対象ごとに別の文面を用意できる。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 生成のときに場面の切れ目へ置かせる行。`layout_novel_text` が空行二つに置き換える。
SCENE_BREAK = "◇"

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


# 空行一つは話し手や流れの切れ目、空行二つ以上と「◇」の行は場面の切れ目として読む。
# 読点も文の切れ目も無い長い文は、折り返さずに残す。半角の「?」「!」は全角にそろえる。
def layout_novel_text(text: str) -> str:
    scenes = []
    text = re.sub(r"(?<=[?!]) +(?=\S)", "", text.replace("\r\n", "\n")).translate(_FULL_WIDTH_MARKS)
    marked = re.sub(rf"^[ \t　]*{SCENE_BREAK}[ \t　]*$", "\n\n\n", text, flags=re.M)
    for scene in re.split(r"\n[ \t　]*\n(?:[ \t　]*\n)+", marked.strip()):
        if not scene.strip():
            continue
        beats = [beat for beat in re.split(r"\n[ \t　]*\n", scene.strip()) if beat.strip()]
        scenes.append("\n\n".join(
            "\n".join(wrapped for line in _join_wrapped_lines(beat.splitlines())
                      for sentence in _split_sentences(line) for wrapped in _wrap(sentence))
            for beat in beats))
    return "\n\n\n".join(scenes)


@dataclass(frozen=True)
class StyleInstruction:
    base: str = ""
    extra: str = ""

    @property
    def text(self) -> str:
        return "\n".join(part.strip() for part in (self.base, self.extra) if part.strip())


# --- 共通(どの文にも効く文体) ---------------------------------------------
# 世界の舞台設定や、既存の話から抽出した文体の癖は、世界ごとに違う「ユーザーの好み」なので
# ここには置かない。呼び出し側(親リポジトリ)が style_instruction() の shared_extra / extra で渡す。

SHARED_STYLE_BASE = """\
語の選び方・文の運び方は、この世界の文章すべてで揃える。
修飾を重ねない。抽象名詞で言い換えず、物と動作の名前で書く。
同じ語・同じ言い回しを近い距離で繰り返さない。

基本的な文体はライトノベルを参考にする。"""


# --- 対象ごと --------------------------------------------------------------

EPISODE_STYLE_BASE = f"""\
本文は地の文と会話文を交ぜ、地の文に寄せすぎない。
情景は視点人物が実際に見聞きした範囲で書き、説明のための地の文を挟まない。
セリフは人物ごとの口調の差が読み分けられる長さで切る。
地の文は一文ごとに改行する。セリフは、中に文がいくつあっても「」ごと一行にする(長い行は清書のときに折り返される)。
空行は、話し手や流れが変わるところにだけ一つ置き、ほかでは空けない。
一人の人物の言動が続くあいだは、そのセリフと、誰が言ったか・どう動いたかの地の文を、空行を挟まず改行だけで続ける。
描写の細かさは中身の重さで変える。筋が動くところ・人物の気持ちが揺れるところは、動作・セリフ・間を一つずつ追って細かく書く。
移動・待ち時間・繰り返しの作業のように筋が動かないところは、一〜二文で飛ばす。
情景は、視点人物の目に留まった物を一か所に一つか二つだけ書き、見えるものを並べ立てない。
気持ちは地の文で説明しきらず、動作・セリフに出す分と、書かずに読み手へ預ける分を分ける。
締め方は、書いている出来事の中身が終わったかどうかで変える。
中身が終わっていないときは、謎・伏線・この先への期待を残して切る。
中身が終わったときは、余韻を残すか、気の利いた落ちを付けて締める。
場面の数と一場面の長さは決めず、中身に合わせる。場面が変わる(場所・時間・書く対象が変わる)ところにだけ、「{SCENE_BREAK}」だけの行を置く。
字数は、実際に起きることで作る。修飾・言い換え・心情の反芻を足して伸ばさない。
種(key)に場面が足りないときは、足りないぶんを場面として立ててから書く。
種(key)にある出来事は、渡された作品・登場人物・場所・直前の話・関係する設定などの周辺データを踏まえ、具体的な描写・会話・人物の動きまで詳しく書き起こす。"""

STORY_STYLE_BASE = """\
作品の筋書きは読ませる文ではなく、後から段階を測るための文として書く。
段階ごとに一〜二文で、誰と何を巡ってか分かる言い方にする。"""

EVENT_STYLE_BASE = """\
出来事の記録は情景も語り口も持たせず、事実と関係だけで書く。
一文に一件だけ入れ、起きた順に並べる。"""

IDEA_STYLE_BASE = """\
アイデアの説明は、それを知らない読み手が一読で掴める短さにする。
物・制度・技のどれなのかを先に置き、来歴はその後に一文で足す。"""

STYLE_BASES: dict[str, str] = {
    "episode": EPISODE_STYLE_BASE,
    "story": STORY_STYLE_BASE,
    "event": EVENT_STYLE_BASE,
    "idea": IDEA_STYLE_BASE,
}


def style_instruction(target: str, shared_extra: str = "", extra: str = "") -> str:
    """文体の指示を組み立てる。

    ここに定数で置くのは、共通(SHARED_STYLE_BASE)と対象ごと(STYLE_BASES)の固定の文面だけ。
    世界の舞台設定や、既存の話から抽出した文体の癖のような、世界ごとに違う「好み」は定数に持たず、
    呼び出し側(親リポジトリ)が `shared_extra`(共通に効く)・`extra`(この対象だけに効く)として渡す。
    """
    if target not in STYLE_BASES:
        raise ValueError(f"文体の指示が無い対象: {target}")
    shared = StyleInstruction(base=SHARED_STYLE_BASE, extra=shared_extra).text
    own = StyleInstruction(base=STYLE_BASES[target], extra=extra).text
    return "\n".join(text for text in (shared, own) if text)
