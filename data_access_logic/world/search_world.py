#!/usr/bin/env python3
"""語で、物語の中身の表(人物・出来事・アイデア・場所・関係・スキル・ミーム・話・作品)をまたいで行を引く。db だけで読む。
世界の展開(スキル `expand`)が、作者の一言に関わる行を集めるのに使う。

    SearchWorld(words=["疫病", "港熱", "潮風"], story_id=3).show()

語は部分一致で、来歴・呼び名の行にも当てる。表ごとに、当たった語の多い順に `limit_per_table` 件まで返す。
人物には関係の相手・当事者になった出来事・居場所を、出来事には当事者・場所・親の出来事を、場所には親を、
関係には二人を一段広げて `linked` に添える。`story_id` を渡すと、話と作品はその作品と子孫(章・外伝)の分だけにする。
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.label import label_of
from data_access_logic.query import common_query, world_search_query
from data_access_logic.query.world_search_query import SearchedTable
from data_access_logic.world.record import LinkedRow, WorldHit, WorldHits
from db.schema import (
    Base, Character, CharacterLocation, CharacterRelation, Event, EventCharacter, Location,
)

# 抜き書きに語の前後を何字ずつ添えるか
_EXCERPT_MARGIN = 30
# 一段広げる出来事の数
_LINKED_EVENT_COUNT = 5


def _ref(row: Base, via: str) -> LinkedRow:
    model = type(row)
    return LinkedRow(table=model.__tablename__, id=row.id, label=label_of(model, row),
                     origin=getattr(row, "origin", None), via=via)


def _texts(table: SearchedTable, row: Base) -> list[str]:
    texts = [getattr(row, column) or "" for column in table.columns]
    if table.histories is not None:
        name, columns = table.histories
        texts += [getattr(history, column) or "" for history in getattr(row, name) for column in columns]
    return texts


def _excerpts(texts: Iterable[str], words: list[str]) -> tuple[list[str], list[str]]:
    found: list[str] = []
    excerpts: list[str] = []
    for text in texts:
        for word in words:
            match = re.search(re.escape(word), text, re.IGNORECASE)
            if match is None:
                continue
            if word not in found:
                found.append(word)
            start, end = max(match.start() - _EXCERPT_MARGIN, 0), match.end() + _EXCERPT_MARGIN
            excerpt = " ".join(text[start:end].split())
            if excerpt not in excerpts:
                excerpts.append(excerpt)
    return found, excerpts


def _linked(s: Session, row: Base) -> list[LinkedRow]:
    match row:
        case Character():
            linked = []
            for relation in s.scalars(world_search_query.relations_of_select(row.id)).all():
                other_id = relation.character_2_id if relation.character_1_id == row.id else relation.character_1_id
                linked.append(_ref(s.get_one(Character, other_id), f"関係「{relation.relation}」"))
            linked += [_ref(event, "当事者になった出来事") for event in s.scalars(
                common_query.events_of_character_select(row.id, limit=_LINKED_EVENT_COUNT)).all()]
            places = s.scalars(select(CharacterLocation).where(CharacterLocation.character_id == row.id)
                               .order_by(CharacterLocation.start.desc().nulls_last())).all()
            linked += [_ref(s.get_one(Location, place.location_id), "居場所") for place in places[:1]]
            return linked
        case Event():
            linked = [_ref(s.get_one(Character, link.character_id), "当事者") for link in s.scalars(
                select(EventCharacter).where(EventCharacter.event_id == row.id).order_by(EventCharacter.id)).all()]
            if row.location_id is not None:
                linked.append(_ref(s.get_one(Location, row.location_id), "場所"))
            if row.parent_event_id is not None:
                linked.append(_ref(s.get_one(Event, row.parent_event_id), "親の出来事"))
            return linked
        case Location() if row.parent_id is not None:
            return [_ref(s.get_one(Location, row.parent_id), "親の場所")]
        case CharacterRelation():
            return [_ref(s.get_one(Character, row.character_1_id), "関係の主体"),
                    _ref(s.get_one(Character, row.character_2_id), "関係の相手")]
        case _:
            return []


class SearchWorld(SessionEntrypoint):
    def __init__(self, words: list[str], story_id: int | None = None, limit_per_table: int = 10):
        self.words = [word.strip() for word in words if word.strip()]
        self.story_id = story_id
        self.limit_per_table = limit_per_table

    def execute(self, s: Session) -> WorldHits:
        if not self.words:
            raise ValueError("words が空")
        story_ids = None if self.story_id is None else common_query.descendant_story_ids(s, self.story_id)
        hits = []
        for table in world_search_query.SEARCHED_TABLES:
            found = []
            for row in s.scalars(world_search_query.hits_select(table, self.words, story_ids)).all():
                words, excerpts = _excerpts(_texts(table, row), self.words)
                found.append((len(words), row, words, excerpts))
            found.sort(key=lambda item: -item[0])
            for _, row, words, excerpts in found[:self.limit_per_table]:
                model = type(row)
                hits.append(WorldHit(table=model.__tablename__, id=row.id, label=label_of(model, row),
                                     origin=getattr(row, "origin", None), words=words, excerpts=excerpts,
                                     linked=_linked(s, row)))
        return WorldHits(hits=hits)
