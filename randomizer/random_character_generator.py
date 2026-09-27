#!/usr/bin/env python3
from __future__ import annotations

import factory

from db.schema import CHARACTER_KIND_PERSON, PERSONALITY_LEVELS

_SEX_CHOICES = ("男", "女", "不定")
_BUILD_CHOICES = ("細身", "小柄", "がっしり", "長身", "ふくよか", "痩身")
_TONE_CHOICES = ("丁寧", "ぶっきらぼう", "早口", "のんびり", "無口", "高圧的")
_FIRST_PERSON_CHOICES = ("わたし", "俺", "僕", "あたし", "自分", "うち")
_SECOND_PERSON_CHOICES = ("あなた", "君", "お前", "そちら", "あんた")
_THIRD_PERSON_CHOICES = ("さん", "くん", "ちゃん", "殿", "氏")



def _personality():
    return factory.Faker("random_element", elements=PERSONALITY_LEVELS)


class ParameterFactory(factory.DictFactory):
    """期間を限らない(start・end が空の)一行。"""

    class Meta:
        # `build` は CharacterParameter の列名(体格)と `Factory.build()` が衝突するので、
        # 下の `build_` で宣言して辞書の `build` キーへ流し込む。
        rename = {"build_": "build"}

    start = None
    end = None

    # 名字は出自・身分・土地柄で決まるので、サイコロでは引かず名づけのときに決める
    family_name = None
    sex = factory.Faker("random_element", elements=_SEX_CHOICES)
    height = factory.Faker("pyfloat", min_value=140, max_value=195, right_digits=1, positive=True)
    build_ = factory.Faker("random_element", elements=_BUILD_CHOICES)

    first_person = factory.Faker("random_element", elements=_FIRST_PERSON_CHOICES)
    second_person = factory.Faker("random_element", elements=_SECOND_PERSON_CHOICES)
    third_person = factory.Faker("random_element", elements=_THIRD_PERSON_CHOICES)
    tone = factory.Faker("random_element", elements=_TONE_CHOICES)

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


class CharacterFactory(factory.DictFactory):
    """誕生・死亡は列を持たず、下の `parameters`(期間を限らない一行)の start / end で表す。"""

    name = factory.Sequence(lambda n: f"仮名{n}")
    text = ""
    kind = CHARACTER_KIND_PERSON

    parameters = factory.LazyFunction(lambda: [ParameterFactory.build()])


def build_parameter(**overrides) -> dict:
    return ParameterFactory.build(**overrides)


def build_character(**overrides) -> dict:
    return CharacterFactory.build(**overrides)
