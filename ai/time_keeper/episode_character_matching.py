#!/usr/bin/env python3
"""話の視点・場所を、自由記述の名前から Character/Location の id へ解決する。

AI が JSON で答える視点(「ノア(十四歳)」「アウレア / ミレア」のような文字列)・場所を
`Episode.viewpoint_character_id` / `Episode.place_id` へ入れる前に、この照合を通す。
db/alembic の移行(既存データの一括変換)と同じロジックだが、alembic はアプリコードに
依存させない方針のため、ここに独立して持つ(呼ぶ側だけが重なる)。
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.schema import Character, Location

_VIEWPOINT_SEP_RE = re.compile(r"[/／]")
_TRAILING_PAREN_RE = re.compile(r"[（(][^（）()]*[）)]\s*\Z")
_WHITESPACE_RE = re.compile(r"[ 　]+")


def match_viewpoint_character_id(session: Session, viewpoint: str | None) -> int | None:
    """視点の自由記述から Character.id を探す。「/」「／」区切りの先頭の1人だけを見て、
    末尾の丸括弧(半角・全角)を落として完全一致で探す。1件だけ当たれば採用、それ以外は None。
    """
    if not viewpoint:
        return None
    first = _VIEWPOINT_SEP_RE.split(viewpoint, 1)[0]
    name = _TRAILING_PAREN_RE.sub("", first).strip()
    if not name:
        return None
    matches = session.scalars(select(Character.id).where(Character.name == name)).all()
    return matches[0] if len(matches) == 1 else None


def match_place_id(session: Session, place: str | None) -> int | None:
    """場所の自由記述から Location.id を探す。まず完全一致、無ければ空白(半角・全角)区切りの
    先頭トークンで完全一致を探す。1件だけ当たれば採用、それ以外は None。
    """
    if not place:
        return None

    def find(name: str) -> int | None:
        matches = session.scalars(select(Location.id).where(Location.name == name)).all()
        return matches[0] if len(matches) == 1 else None

    exact = find(place)
    if exact is not None:
        return exact
    token = _WHITESPACE_RE.split(place.strip(), 1)[0]
    if token and token != place:
        return find(token)
    return None
