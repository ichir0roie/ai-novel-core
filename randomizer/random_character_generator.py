#!/usr/bin/env python3
from __future__ import annotations

import factory

from data_access_logic.character.form import CharacterCreateForm
from data_access_logic.character.record import CharacterParameterRow
from db.schema import CHARACTER_KIND_PERSON, PERSONALITY_LEVELS


def _personality() -> factory.Faker:
    return factory.Faker("random_element", elements=PERSONALITY_LEVELS)


class ParameterFactory(factory.Factory):
    """期間を限らない(start・end が空の)一行。"""

    class Meta:
        model = CharacterParameterRow
        # `build` は CharacterParameter の列名(体格)と `Factory.build()` が衝突するので、
        # 下の `build_` で宣言して `build` の欄へ流し込む。
        rename = {"build_": "build"}

    start = None
    end = None

    # 名字は出自・身分・土地柄で決まるので、サイコロでは引かず名づけのときに決める。
    # 性別・体格・一人称・二人称・三人称・口調も、少ない候補からサイコロで引くと種類が偏るので、
    # ここでは None のままにし、人物説明に合わせて AI が自分で考えて決める
    # (data_access_logic/character/generator.py の `generate_character` 側)。
    family_name = None
    sex = None
    height = factory.Faker("pyfloat", min_value=140, max_value=195, right_digits=1, positive=True)
    build_ = None

    first_person = None
    second_person = None
    third_person = None
    tone = None

    sincerity = _personality()
    curiosity = _personality()
    proactivity = _personality()
    cooperativeness = _personality()
    sociability = _personality()
    emotional_expression = _personality()
    self_esteem = _personality()
    self_efficacy = _personality()
    stress_resilience = _personality()
    flexibility_of_values = _personality()
    sensitivity = _personality()
    imagination = _personality()


class CharacterFactory(factory.Factory):
    """誕生・死亡は列を持たず、下の `parameters`(期間を限らない一行)の start / end で表す。"""

    class Meta:
        model = CharacterCreateForm

    name = factory.Sequence(lambda n: f"仮名{n}")
    kind = CHARACTER_KIND_PERSON

    parameters = factory.LazyFunction(lambda: [ParameterFactory.build()])


def build_character(**overrides) -> CharacterCreateForm:
    return CharacterFactory.build(**overrides)
