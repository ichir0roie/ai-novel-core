#!/usr/bin/env python3
"""話の登場人物の候補。Claude が登場人物を決める材料(`brief.episode_casting`)に出す。"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from data_access_logic.episode.mentions import cast_characters
from data_access_logic.query import common_query
from data_access_logic.query.period import alive_at
from db.schema import Character, CharacterRelation, Episode
from db.stamp import Stamp


def _related_ids(s: Session, cast_ids: set[int], time: Stamp) -> list[int]:
    relations = s.scalars(
        select(CharacterRelation)
        .where(or_(CharacterRelation.character_1_id.in_(cast_ids), CharacterRelation.character_2_id.in_(cast_ids)),
               alive_at(CharacterRelation, time))
        .order_by(CharacterRelation.id)
    ).all()
    return [character_id for relation in relations
            for character_id in (relation.character_1_id, relation.character_2_id)]


def _resident_ids(s: Session, location_id: int | None, time: Stamp) -> list[int]:
    if location_id is None:
        return []
    location_ids = common_query.descendant_location_ids(s, location_id)
    return list(s.scalars(common_query.resident_character_ids_select(location_ids, time)).all())


def candidate_characters(
    s: Session, episode: Episode, excluded_ids: set[int], location_id: int | None, time: Stamp,
) -> list[Character]:
    """登場人物と関係のある人物・話の場所(とその中)にいる人物。プロット・本文に名前が出る人物は、保存のたびに
    名前だけ出る人物(`mentioned` の行)として拾い直してあり、候補とは別に出す。

    `episode` は `episode_characters` と `EpisodeCharacter.character` を読んだもの。"""
    cast_ids = {character.id for character in cast_characters(episode)}
    candidate_ids = [
        *_related_ids(s, cast_ids, time),
        *_resident_ids(s, location_id, time),
    ]
    return list(s.scalars(
        select(Character)
        .where(Character.id.in_([character_id for character_id in candidate_ids if character_id not in excluded_ids]))
        .order_by(Character.id)
    ).all())
