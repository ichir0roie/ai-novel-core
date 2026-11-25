#!/usr/bin/env python3
"""人物モード(`SimulateDay`)を試す世界を、テスト用の db に factory_boy で一回で作る。

エリア(詳細でない町)・その下の詳細の場所・そこに住む人物(年齢・口調・欲の段・行動力)・人物どうしの関係・モチベーション・
前の日までの一日の記録・作者の予定を、パターン(`PATTERNS`)か `WorldSpec` で渡して作り、作った行の id を返す。

    .venv/bin/python -m tool.test.day_world --pattern basic        # 作って id を JSON で出す
    .venv/bin/python -m tool.test.day_world --list                 # パターンの一覧

pytest からは `build_day_world(WorldSpec(...))` を呼ぶ(`tool.test` を先に読んであるので、db はテスト用の db に固定される)。
"""
from __future__ import annotations

from tool.test import ensure_test_db  # schema より先に読む(db をテスト用の db に固定する)

import argparse
import json
from dataclasses import asdict, dataclass, field

from factory.random import reseed_random

from db.schema import CHARACTER_KIND_PERSON, engine
from db.stamp import Stamp
from randomizer import mock_factories

# 一つ目の場所から順に、人物の家にする
_PLACES = (
    ("一の家", "家", "坂の下の小さな家"),
    ("二の家", "家", "坂の上の古い家"),
    ("パン屋", "店", "朝いちばんにパンが焼ける店"),
    ("朝の市場", "市場", "波止場の前の市場。朝に魚と野菜が並ぶ"),
    ("酒場", "酒場", "昼は食堂、夜は酒場"),
    ("広場", "広場", "子どもと猫が集まる広場"),
    ("井戸端", "井戸", "坂の途中の井戸。人が立ち話をする"),
)


@dataclass
class PastDays:
    """その日より前の何日かの、一日の記録(どの日も同じ値)。"""

    days: int
    food: int = 100
    sleep: int = 100
    touch: int = 100
    load: int = 0
    bedtime: int = 24


@dataclass
class PersonSpec:
    name: str
    age: int
    # 住まい。`_PLACES` の番号
    home: int
    text: str
    first_person: str = "わたし"
    tone: str = "ふつうの口調"
    sex: str = "女"
    proactivity: str = "並"
    # 空なら人物モードが年齢から決める
    appetite: str | None = None
    sleep_drive: str | None = None
    libido: str | None = None
    motivations: list[tuple[str, int]] = field(default_factory=list)
    past: PastDays | None = None


@dataclass
class FixedSpec:
    """作者の予定(出来事)。`people` は人物の番号、`place` は `_PLACES` の番号。"""

    name: str
    text: str
    hour: int
    hours: int
    place: int
    people: list[int]


@dataclass
class WorldSpec:
    people: list[PersonSpec]
    date: str = "1200/06/10"
    # 一人目と二人目の関係
    relation: str | None = "幼なじみ"
    relation_text: str = "同じ坂で育った"
    fixed: list[FixedSpec] = field(default_factory=list)
    seed: int = 0


@dataclass
class DayWorld:
    date: str
    town_id: int
    place_ids: list[int]
    character_ids: list[int]
    event_ids: list[int]


def _pair(first_changes: dict | None = None, second_changes: dict | None = None) -> list[PersonSpec]:
    """幼なじみの二人(パン屋の娘と漁師見習い)。渡した欄だけ変える。"""
    first = dict(name="ミオ", age=17, home=0, sex="女", first_person="あたし", tone="明るくはきはきした口調",
                 text="パン屋で働く娘。幼なじみのカイが漁師見習いになってから、あまり話せていないのが気になっている。",
                 proactivity="高", motivations=[("カイとまた昔みたいに話したい", 3)])
    second = dict(name="カイ", age=18, home=1, sex="男", first_person="俺", tone="ぶっきらぼうだが優しい口調",
                  text="漁師見習い。祖父と二人暮らし。早く一人前になって祖父を楽にさせたい。",
                  proactivity="並", motivations=[("一人前の漁師として認められたい", 4)])
    return [PersonSpec(**{**first, **(first_changes or {})}), PersonSpec(**{**second, **(second_changes or {})})]


PATTERNS: dict[str, WorldSpec] = {
    # 前の日の記録の無い、ふつうの二人
    "basic": WorldSpec(people=_pair()),
    # 一人は七日の眠りが足りず、もう一人は七日の行動量が上限に近い
    "tired": WorldSpec(people=_pair(dict(past=PastDays(days=6, sleep=55, load=20)),
                                    dict(proactivity="低", past=PastDays(days=6, load=13)))),
    # 昼すぎに市場で二人が会う予定がある
    "meeting": WorldSpec(people=_pair(), fixed=[FixedSpec(
        name="市場での待ち合わせ", text="ミオとカイが市場で落ち合い、祭りの飾りを買う", hour=15, hours=2, place=3, people=[0, 1])]),
    # 子どもと年寄り(欲の段は年齢から決まる)。同じ家に住む
    "family": WorldSpec(relation="祖父と孫", relation_text="祖父が孫を育てている", people=[
        PersonSpec(name="ハル", age=9, home=0, sex="男", first_person="ぼく", tone="元気な子どもの口調",
                   text="漁師町の男の子。祖父と暮らす。広場で遊ぶのが好き。", proactivity="高",
                   motivations=[("広場で一番の石投げになりたい", 2)]),
        PersonSpec(name="ゲン", age=72, home=0, sex="男", first_person="わし", tone="のんびりした年寄りの口調",
                   text="元漁師の年寄り。孫のハルを育てている。膝が悪い。", proactivity="低",
                   motivations=[("ハルが一人前になるまで見届けたい", 3)]),
    ]),
}


def _born(date: Stamp, age: int) -> Stamp:
    year, month, day = date.western_digits[:3]
    return Stamp.western(year - age, max(1, month - 1), day)


def build_day_world(spec: WorldSpec) -> DayWorld:
    """`spec` の世界を足して、作った行の id を返す。行は毎回新しく足すので、何度呼んでも前の世界と混ざらない。"""
    reseed_random(spec.seed)
    date = Stamp.parse(spec.date)
    assert date is not None
    mock_factories.bind(engine)
    try:
        planet = mock_factories.LocationFactory(name="試しの星", kind="星", parent_id=None, map_detail=False,
                                                start="1000", end=None)
        town = mock_factories.LocationFactory(name="試しの港町", kind="町", parent_id=planet.id, map_detail=False,
                                              text="小さな港町", start="1100", end=None)
        places = [mock_factories.LocationFactory(name=name, kind=kind, text=text, parent_id=town.id, map_detail=True,
                                                 start="1100", end=None) for name, kind, text in _PLACES]
        characters = []
        for person in spec.people:
            character = mock_factories.CharacterFactory(
                name=person.name, kind=CHARACTER_KIND_PERSON, main_character=False, text=person.text,
                start=_born(date, person.age), end=None)
            row = character.parameters[0]
            for key in ("sex", "first_person", "tone", "proactivity", "appetite", "sleep_drive", "libido"):
                setattr(row, key, getattr(person, key))
            row.second_person, row.third_person, row.dialect = "あんた", "あの人", "標準語"
            mock_factories.CharacterLocationFactory(character_id=character.id, location_id=places[person.home].id,
                                                    start=_born(date, person.age), end=None)
            for text, strength in person.motivations:
                mock_factories.CharacterMotivationFactory(character_id=character.id, text=text, strength=strength,
                                                          start=date.plus_days(-30), end=None)
            if person.past is not None:
                for days in range(1, person.past.days + 1):
                    mock_factories.CharacterDayFactory(
                        character_id=character.id, date=date.plus_days(-days), food=person.past.food,
                        sleep=person.past.sleep, touch=person.past.touch, load=person.past.load,
                        bedtime=person.past.bedtime)
            characters.append(character)
        if spec.relation is not None and len(characters) >= 2:
            mock_factories.CharacterRelationFactory(
                character_1_id=characters[0].id, character_2_id=characters[1].id, relation=spec.relation,
                text=spec.relation_text, start=date.plus_days(-3650))
        events = []
        year, month, day = date.western_digits[:3]
        for fixed in spec.fixed:
            event = mock_factories.EventFactory(
                name=fixed.name, text=fixed.text, time=Stamp.western(year, month, day, fixed.hour),
                end=Stamp.western(year, month, day, fixed.hour + fixed.hours), location_id=places[fixed.place].id,
                parent_event_id=None, hidden=False)
            for index in fixed.people:
                mock_factories.EventCharacterFactory(event_id=event.id, character_id=characters[index].id)
            events.append(event)
        mock_factories.commit()
        return DayWorld(date=spec.date, town_id=town.id, place_ids=[place.id for place in places],
                        character_ids=[character.id for character in characters], event_ids=[event.id for event in events])
    finally:
        mock_factories.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", choices=sorted(PATTERNS), default="basic")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--list", action="store_true", help="パターンの一覧を出す")
    args = parser.parse_args()
    if args.list:
        for name, spec in PATTERNS.items():
            print(name, json.dumps(asdict(spec), ensure_ascii=False))
        return
    ensure_test_db()
    spec = PATTERNS[args.pattern]
    spec.seed = args.seed
    print(json.dumps(asdict(build_day_world(spec)), ensure_ascii=False))


if __name__ == "__main__":
    main()
