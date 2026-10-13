#!/usr/bin/env python3
"""人物ごとの居場所。ロケーション別ツリー(画面 `/tables/character?view=tree`)の元データ。"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from data_access_logic.query.period import alive_at
from db.schema import Character, CharacterLocation
from db.stamp import Stamp


def _sort_key(character_location: CharacterLocation) -> tuple:
    # start が無い(「初めから」)行は一番古い扱いにする
    return (character_location.start is not None, character_location.start.to_int() if character_location.start is not None else 0, character_location.id)


def latest_location_ids(s: Session, time: Stamp | None = None) -> dict[int, int]:
    """人物 id → 一番新しく設定された居場所(location の id)。居場所を一つも持たない人物は含まない。

    `time` を渡せば、その時刻に効いている居場所のうち一番新しく始まったものにし、その時刻に居場所の無い人物と、
    没年(`Character.end`)を過ぎた人物は含まない。
    """
    query = select(CharacterLocation)
    if time is not None:
        query = (query.join(Character, Character.id == CharacterLocation.character_id)
                 .where(alive_at(CharacterLocation, time), or_(Character.end.is_(None), Character.end > time)))
    latest: dict[int, CharacterLocation] = {}
    for character_location in s.scalars(query):
        if character_location.character_id is None:
            continue
        current = latest.get(character_location.character_id)
        if current is None or _sort_key(character_location) > _sort_key(current):
            latest[character_location.character_id] = character_location
    return {character_id: character_location.location_id for character_id, character_location in latest.items()}
