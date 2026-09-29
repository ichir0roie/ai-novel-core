#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select

from data_access_logic.character.parameters import parameters_at
from db.schema import Character, CharacterRelation

__all__ = ["character_dict", "relation_dict", "collect_relations"]


def _year(stamp) -> int | None:
    return None if stamp is None else stamp.year


def character_dict(character) -> dict:
    return {
        "id": character.id, "name": character.name, "kind": character.kind,
        "sex": parameters_at(character, None).sex,
        "start": _year(character.start), "end": _year(character.end),
        "link": f"/tables/character/{character.id}",
    }


def relation_dict(relation) -> dict:
    return {
        "id": relation.id,
        "character_id_1": relation.character_id_1,
        "character_id_2": relation.character_id_2,
        "relation": relation.relation,
        "start": _year(relation.start), "end": _year(relation.end),
        "text": relation.text or "",
    }


def collect_relations(session) -> dict:
    characters = session.scalars(select(Character).order_by(Character.id)).all()
    relations = session.scalars(select(CharacterRelation).order_by(CharacterRelation.id)).all()
    return {
        "characters": [character_dict(c) for c in characters],
        "relations": [relation_dict(r) for r in relations],
    }
