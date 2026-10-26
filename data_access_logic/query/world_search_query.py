#!/usr/bin/env python3
"""語で、物語の中身の表をまたいで行を引く(`world.search_world.SearchWorld`)。"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, false, or_, select

from db.schema import (
    Base, Character, CharacterHistory, CharacterRelation, CharacterRelationHistory, CharacterSkill, Episode, Event,
    Idea, IdeaHistory, Location, LocationHistory, Meme, Story,
)


@dataclass(frozen=True)
class SearchedTable:
    model: type[Base]
    # 語を当てる列
    columns: tuple[str, ...]
    # 来歴・呼び名の子の行(relationship の名前)と、語を当てるその列
    histories: tuple[str, tuple[str, ...]] | None = None


SEARCHED_TABLES: tuple[SearchedTable, ...] = (
    SearchedTable(Character, ("name", "appearance", "text", "plot"), ("histories", ("description",))),
    SearchedTable(Event, ("name", "text")),
    SearchedTable(Idea, ("name", "text"), ("histories", ("name", "detail"))),
    SearchedTable(Location, ("name", "text"), ("histories", ("description",))),
    SearchedTable(CharacterRelation, ("relation", "text"), ("histories", ("description",))),
    SearchedTable(CharacterSkill, ("name", "text")),
    SearchedTable(Meme, ("text",)),
    SearchedTable(Episode, ("title", "plot_text")),
    SearchedTable(Story, ("name", "text")),
)

_HISTORY_MODELS: dict[type[Base], type[Base]] = {
    Character: CharacterHistory, Idea: IdeaHistory, Location: LocationHistory, CharacterRelation: CharacterRelationHistory,
}


def _matches(model: type[Base], columns: tuple[str, ...], words: list[str]) -> list[ColumnElement[bool]]:
    return [getattr(model, column).ilike(f"%{word}%") for column in columns for word in words]


def hits_select(table: SearchedTable, words: list[str], story_ids: list[int] | None) -> Select:
    conditions = _matches(table.model, table.columns, words)
    if table.histories is not None:
        name, columns = table.histories
        conditions.append(getattr(table.model, name).any(or_(*_matches(_HISTORY_MODELS[table.model], columns, words))))
    query = select(table.model).where(or_(*conditions) if conditions else false()).order_by(table.model.id)
    if story_ids is not None and table.model is Episode:
        query = query.where(Episode.story_id.in_(story_ids))
    if story_ids is not None and table.model is Story:
        query = query.where(Story.id.in_(story_ids))
    return query


def relations_of_select(character_id: int) -> Select:
    return (select(CharacterRelation)
            .where(or_(CharacterRelation.character_1_id == character_id, CharacterRelation.character_2_id == character_id))
            .order_by(CharacterRelation.id))
