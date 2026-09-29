#!/usr/bin/env python3
"""人物ごとの、一番新しく設定された居場所。ロケーション別ツリー(画面 `/tables/character?view=tree`)の元データ。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.schema import CharacterLocation


def _sort_key(character_location: CharacterLocation) -> tuple:
    # start が無い(「初めから」)行は一番古い扱いにする
    return (character_location.start is not None, character_location.start.to_int() if character_location.start is not None else 0, character_location.id)


def latest_location_ids(s: Session) -> dict[int, int]:
    """人物 id → 一番新しく設定された居場所(location の id)。居場所を一つも持たない人物は含まない。"""
    latest: dict[int, CharacterLocation] = {}
    for character_location in s.scalars(select(CharacterLocation)):
        current = latest.get(character_location.character_id)
        if current is None or _sort_key(character_location) > _sort_key(current):
            latest[character_location.character_id] = character_location
    return {character_id: character_location.location_id for character_id, character_location in latest.items()}
