#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.character.form import BaseCharacterSearchForm
from data_access_logic.character.models import LEVEL_AXES
from data_access_logic.character.parameters import parameters_at
from data_access_logic.character.record import BaseCharacterMatch
from data_access_logic.entrypoint import SessionEntrypoint
from db.schema import Character, PersonalityLevel

_ORDER = list(PersonalityLevel)


class FindBaseCharacters(SessionEntrypoint):
    """作品に置いた人物(実在の人物などの素体)を、望む性格の段階に近い順に並べる。新しい人物を作る前に、
    望む特性を持つ人物の芯・ミーム・行動原理を見比べる材料にする。

    `traits` の軸ごとに、人物の段階と望む段階の隔たり(無/低/並/高/必 の一段を 1)を足した `distance` の小さい順、
    同じなら一致した軸の多い順に返す。人物が決めていない軸は「並」として数える。`words` と `sex` は絞り込み。
    """

    def __init__(self, search: BaseCharacterSearchForm):
        self.search = search

    def execute(self, s: Session) -> list[BaseCharacterMatch]:
        search = self.search
        rows = s.scalars(select(Character).where(Character.story_id == search.story_id)
                         .order_by(Character.id).execution_options(populate_existing=True)).all()
        matches = []
        for row in rows:
            values = parameters_at(row, None)
            if search.sex is not None and values.sex != search.sex:
                continue
            haystack = " ".join(filter(None, (row.name, values.family_name, row.text, row.meme, row.principle)))
            if not all(word in haystack for word in search.words):
                continue
            levels = {column: getattr(values, column) for column in LEVEL_AXES}
            gaps = {column: abs(_ORDER.index(levels[column] or PersonalityLevel.NORMAL) - _ORDER.index(wanted))
                    for column, wanted in search.traits.items()}
            matches.append(BaseCharacterMatch(
                id=row.id, name=row.name, family_name=values.family_name, sex=values.sex,
                start=row.start, end=row.end, text=row.text, meme=row.meme, principle=row.principle,
                levels={LEVEL_AXES[column]: level for column, level in levels.items() if level is not None},
                distance=sum(gaps.values()),
                matched=[LEVEL_AXES[column] for column, gap in gaps.items() if gap == 0]))
        matches.sort(key=lambda match: (match.distance, -len(match.matched), match.id))
        return matches[:search.limit]
