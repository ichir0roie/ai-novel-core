#!/usr/bin/env python3
"""人物ごとの、一番新しく設定された居場所。ロケーション別ツリー(画面 `/tables/character?view=tree`)の元データ。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.schema import CharacterPlace

__all__ = ["collect_character_locations"]


def _sort_key(place: CharacterPlace) -> tuple:
    # start が無い(「初めから」)行は一番古い扱いにする
    return (place.start is not None, place.start.to_int() if place.start is not None else 0, place.id)


def collect_character_locations(session: Session) -> dict[int, int]:
    """人物 id → 一番新しく設定された居場所(location の id)。居場所を一つも持たない人物は含まない。"""
    latest: dict[int, CharacterPlace] = {}
    for place in session.scalars(select(CharacterPlace)):
        current = latest.get(place.character_id)
        if current is None or _sort_key(place) > _sort_key(current):
            latest[place.character_id] = place
    return {character_id: place.location_id for character_id, place in latest.items()}
