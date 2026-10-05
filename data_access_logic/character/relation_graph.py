#!/usr/bin/env python3
"""人物相関図の元データ。GUI の画面(`/relations`)が描く。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.character.parameters import parameters_at
from db.schema import Character, CharacterRelation
from db.stamp import Stamp

# 人物相関図の色。地図の色は区分ごとの `map.category.CATEGORY_COLORS`
RELATION_COLORS = ("#c0392b", "#2471a3", "#1e8449", "#b9770e", "#7d3c98",
                   "#148f77", "#a04000", "#5d6d7e", "#d4ac0d", "#884ea0")


class RelationCharacter(BaseModel):
    id: int
    name: str | None
    kind: str | None
    sex: str | None
    start: int | None
    end: int | None
    link: str


class Relation(BaseModel):
    id: int
    character_1_id: int
    character_2_id: int
    relation: str | None
    start: int | None
    end: int | None
    text: str


class RelationGraph(BaseModel):
    characters: list[RelationCharacter]
    relations: list[Relation]


def _year(stamp: Stamp | None) -> int | None:
    return None if stamp is None else stamp.year


def relation_character_of(character: Character) -> RelationCharacter:
    return RelationCharacter(id=character.id, name=character.name, kind=character.kind,
                             sex=parameters_at(character, None).sex,
                             start=_year(character.start), end=_year(character.end),
                             link=f"/tables/character/{character.id}")


def relation_of(relation: CharacterRelation) -> Relation:
    return Relation(id=relation.id, character_1_id=relation.character_1_id, character_2_id=relation.character_2_id,
                    relation=relation.relation, start=_year(relation.start), end=_year(relation.end),
                    text=relation.text or "")


def relation_graph(s: Session) -> RelationGraph:
    characters = s.scalars(select(Character).order_by(Character.id)).all()
    relations = s.scalars(select(CharacterRelation).order_by(CharacterRelation.id)).all()
    return RelationGraph(characters=[relation_character_of(character) for character in characters],
                         relations=[relation_of(relation) for relation in relations])
