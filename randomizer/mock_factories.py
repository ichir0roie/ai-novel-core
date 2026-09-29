#!/usr/bin/env python3
from __future__ import annotations

import factory
from factory.random import randgen
from sqlalchemy import select
from sqlalchemy.orm import scoped_session, sessionmaker

from db.schema import (
    CHARACTER_KIND_PERSON,
    Base, Character, CharacterParameter, CharacterPlace, Episode, Event, EventCharacter,
    Idea, Location, Story,
)
from db.stamp import Stamp
from randomizer.random_character_generator import _personality

_session = scoped_session(sessionmaker())

_LOCALE = "ja_JP"
_YEAR_RANGE = (4000, 5000)

# 実際の生成(data_access_logic/character/generator.py)は人物説明に合わせて AI が自分で
# 決めるが、ここは db にそれらしい見た目のダミー行を積むだけの目的なので、少ない候補からのサイコロでよい。
_SEX_CHOICES = ("男", "女", "不定")
_BUILD_CHOICES = ("細身", "小柄", "がっしり", "長身", "ふくよか", "痩身")
_TONE_CHOICES = ("丁寧", "ぶっきらぼう", "早口", "のんびり", "無口", "高圧的")
_FIRST_PERSON_CHOICES = ("わたし", "俺", "僕", "あたし", "自分", "うち")
_SECOND_PERSON_CHOICES = ("あなた", "君", "お前", "そちら", "あんた")
_THIRD_PERSON_CHOICES = ("さん", "くん", "ちゃん", "殿", "氏")

_LOCATION_KINDS = ("世界線", "惑星", "大陸", "国", "地方", "都市", "町", "村", "森", "山", "海", "島")
_ENVIRONMENTS = ("温帯", "寒帯", "乾燥帯", "熱帯", "高地", "沿岸", "湿地", "砂漠", "凍土")
_SAMPLE_REGIONS = ("北欧", "地中海沿岸", "東アジア", "中東", "南米", "東欧", "東南アジア", "北米平原")
_SAMPLE_CULTURES = ("遊牧", "稲作", "狩猟採集", "交易", "漁労", "牧畜", "都市商業")
_SAMPLE_ERAS = ("古代", "中世", "近世", "産業革命期", "近代", "現代", "近未来")
_CHARACTER_KINDS = (CHARACTER_KIND_PERSON,) * 7 + ("国", "組織", "商会", "氏族", "集団", "物")
_IDEA_KINDS = ("地名", "人名", "組織", "技術", "魔法", "制度", "道具", "生物", "慣習")
_NARRATIONS = ("一人称", "三人称", "神視点")
_STATES = ("構想中", "執筆中", "完結", "中断")


def bind(engine) -> None:
    _session.configure(bind=engine)


def commit() -> None:
    _session.commit()
    _session.remove()


def _random_stamp(after: Stamp | None = None) -> Stamp:
    low = after.year if after is not None else _YEAR_RANGE[0]
    year = randgen.randint(low, max(low, _YEAR_RANGE[1]))
    return Stamp(year, randgen.randint(1, 12), randgen.randint(1, 28),
                 randgen.randint(0, 23), randgen.randint(0, 59), randgen.randint(0, 59))


def _pick_id(model: type[Base], factory_class: type[factory.Factory] | None = None, p_none: float = 0.0) -> int | None:
    if p_none and randgen.random() < p_none:
        return None
    ids = _session().execute(select(model.id)).scalars().all()
    if ids:
        return randgen.choice(ids)
    if factory_class is None:
        return None
    return factory_class().id


def _pool(model: type[Base], factory_name: str | None = None, p_none: float = 0.0) -> factory.LazyFunction:
    # 参照先のファクトリはこの後で定義されるので、名前で持って呼ぶときに引く
    return factory.LazyFunction(
        lambda: _pick_id(model, globals()[factory_name] if factory_name else None, p_none))


def _stamp() -> factory.LazyFunction:
    return factory.LazyFunction(_random_stamp)


def _optional_stamp(p_none: float = 0.3) -> factory.LazyFunction:
    return factory.LazyFunction(
        lambda: None if randgen.random() < p_none else _random_stamp())


def _end_after_start(p_none: float = 0.5) -> factory.LazyAttribute:
    return factory.LazyAttribute(
        lambda o: None if o.start is None or randgen.random() < p_none
        else _random_stamp(after=o.start))


def _text() -> factory.Faker:
    return factory.Faker("text", max_nb_chars=200, locale=_LOCALE)


class _ModelFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session = _session
        sqlalchemy_session_persistence = "flush"


class LocationFactory(_ModelFactory):
    class Meta:
        model = Location

    name = factory.Sequence(lambda n: f"土地{n}")
    kind = factory.Faker("random_element", elements=_LOCATION_KINDS)
    text = _text()
    parent_id = _pool(Location, p_none=0.15)

    location_world = factory.Faker("random_int", min=0, max=9)
    location_planet = factory.Faker("random_int", min=0, max=5)
    location_longitude = factory.Faker("pyfloat", min_value=-180, max_value=180, right_digits=3)
    location_latitude = factory.Faker("pyfloat", min_value=-90, max_value=90, right_digits=3)
    location_altitude = factory.Faker("pyfloat", min_value=0, max_value=3000, right_digits=1)

    area = factory.Faker("pyfloat", min_value=1, max_value=1_000_000, right_digits=1)
    environment = factory.Faker("random_element", elements=_ENVIRONMENTS)
    sample_region = factory.Faker("random_element", elements=_SAMPLE_REGIONS)
    sample_culture = factory.Faker("random_element", elements=_SAMPLE_CULTURES)
    sample_era = factory.Faker("random_element", elements=_SAMPLE_ERAS)

    start = _optional_stamp()
    end = _end_after_start()
    active_random_generation = factory.Faker("pybool")


class CharacterFactory(_ModelFactory):
    class Meta:
        model = Character

    name = factory.Faker("name", locale=_LOCALE)
    kind = factory.Faker("random_element", elements=_CHARACTER_KINDS)
    main_character = factory.Faker("pybool")
    text = _text()

    start = _optional_stamp()
    end = _end_after_start()


class CharacterParameterFactory(_ModelFactory):
    class Meta:
        model = CharacterParameter
        # `build` は CharacterParameter の列名と `Factory.build()` が衝突する
        rename = {"build_": "build"}

    character_id = _pool(Character, "CharacterFactory")
    start = _optional_stamp()
    end = _end_after_start()

    family_name = factory.Faker("last_name", locale=_LOCALE)
    sex = factory.Faker("random_element", elements=_SEX_CHOICES)
    height = factory.Faker("pyfloat", min_value=140, max_value=195, right_digits=1)
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


class EventFactory(_ModelFactory):
    class Meta:
        model = Event

    name = factory.Sequence(lambda n: f"出来事{n}")
    hidden = factory.Faker("boolean", chance_of_getting_true=10)
    text = _text()
    time = _stamp()
    parent_event_id = _pool(Event, p_none=0.3)
    location_id = _pool(Location, "LocationFactory", p_none=0.1)
    start = _optional_stamp()
    end = _end_after_start()


class EventCharacterFactory(_ModelFactory):
    class Meta:
        model = EventCharacter

    event_id = _pool(Event, "EventFactory")
    character_id = _pool(Character, "CharacterFactory")


class CharacterPlaceFactory(_ModelFactory):
    class Meta:
        model = CharacterPlace

    character_id = _pool(Character, "CharacterFactory")
    location_id = _pool(Location, "LocationFactory")
    start = _optional_stamp()
    end = _end_after_start()


class IdeaFactory(_ModelFactory):
    class Meta:
        model = Idea

    name = factory.Sequence(lambda n: f"アイデア{n}")
    kind = factory.Faker("random_element", elements=_IDEA_KINDS)
    text = _text()
    location_id = _pool(Location, "LocationFactory", p_none=0.2)
    start = _optional_stamp()
    end = _end_after_start()
    parent_idea_id = _pool(Idea, p_none=0.3)


class StoryFactory(_ModelFactory):
    class Meta:
        model = Story

    name = factory.Sequence(lambda n: f"作品{n}")
    text = _text()
    world_id = _pool(Location, "LocationFactory", p_none=0.1)
    place_id = _pool(Location, "LocationFactory", p_none=0.1)
    narration = factory.Faker("random_element", elements=_NARRATIONS)
    state = factory.Faker("random_element", elements=_STATES)
    start = _optional_stamp()
    end = _end_after_start()


class EpisodeFactory(_ModelFactory):
    class Meta:
        model = Episode

    story_id = _pool(Story, "StoryFactory")
    title = factory.Faker("sentence", nb_words=4, locale=_LOCALE)
    key = factory.Faker("text", max_nb_chars=200, locale=_LOCALE)
    text = _text()
    synced = factory.Faker("pybool")
    start = _optional_stamp()
    end = _end_after_start()
    viewpoint = factory.Faker("name", locale=_LOCALE)
    place = factory.Faker("city", locale=_LOCALE)


# 外部キーの参照先が先に埋まる順
ALL_FACTORIES = (
    LocationFactory,
    CharacterFactory,
    CharacterParameterFactory,
    EventFactory,
    EventCharacterFactory,
    CharacterPlaceFactory,
    IdeaFactory,
    StoryFactory,
    EpisodeFactory,
)
