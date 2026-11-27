"""人物の決まった居場所(`character_routine`)を AI で下書きする段の材料・出力の形と、db の段。

人物モード(`SimulateDay`)で動かしていない人物は、決まった居場所の行が無いと、住まいにいて昼は留守(どこにもいない)になり、
動かしている人物の目に映らない。決まった居場所の無い人物に、人物像・行動原理・来歴・関係から、毎日通う所と時間を決めさせて足す。
"""
from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.character.cast import age_at, relations_at
from data_access_logic.character.record import CharacterRoutineRow
from data_access_logic.event.plan import _current_location_id
from data_access_logic.expansion.act_models import DayPlace
from data_access_logic.expansion.acting import area_of, places_of
from data_access_logic.material import Material, Timestamp
from data_access_logic.query import common_query, expansion_query, world_creation_query
from data_access_logic.query.period import dated_alive_at
from db.schema import Character, CharacterLocation, CharacterRoutine, Location
from db.stamp import Stamp, active_calendar


class RoutineForm(BaseModel):
    # 名指しした人物
    character_ids: list[int] = []
    # この人物のいるエリア(詳細の場所の一番近い、詳細でない上の場所)の詳細の場所に住む人物も足す(この人物は、名指ししなければ足さない)
    around_character_id: int | None = None
    # いつの人物で決めるか。省けば、名指しした人物(無ければ `around_character_id`)が最後に出た時刻
    time: Stamp | None = None


class RoutineCharacter(Material):
    """決まった居場所を決める人物一人の材料。"""

    character_id: int
    name: str | None = None
    age: int | None = None
    text: str
    principle: str | None = None
    # 来歴(古い順。新しいものから `ROUTINE_HISTORY_LIMIT` 行)
    histories: list[str]
    # 続いている関係(「相手: 間柄」)
    relations: list[str]
    home: DayPlace
    places: list[DayPlace]
    # 時間帯を暦の時に割り直すための、暦の一日の時の数(材料には渡さない)
    hours_per_day: int

    def for_prompt(self) -> dict[str, Any]:
        return {
            "人物": {"名前": self.name, "年齢": self.age, "人物像": self.text, "行動原理": self.principle,
                   "来歴(古い順)": self.histories, "関係": self.relations},
            "住まい": self.home.for_prompt(),
            "行ける場所": [place.for_prompt() for place in self.places],
            "時間帯": [f"{name}({start}〜{end}時ごろ)" for name, (start, end) in constants.ROUTINE_PERIODS.items()],
        }


class RoutineSkipped(BaseModel):
    character_id: int
    name: str | None = None
    reason: str


class RoutineTargets(BaseModel):
    time: Stamp
    characters: list[RoutineCharacter]
    skipped: list[RoutineSkipped]


class RoutineDraftRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str = Field(description=f"そこにいる時間帯。{'・'.join(constants.ROUTINE_PERIODS)} から一つ")
    location_id: int = Field(description="毎日通う場所の場所id。行ける場所の中から")
    text: str = Field(description="そこでしていること。その場に来た人から見える形で短く(「帳場に立って客をさばいている」)")


class RoutineDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routines: list[RoutineDraftRow] = Field(description="毎日決まって過ごす時間帯と場所。時間帯ごとに一つまで。決まって通う所が無ければ空")


class RoutineAddForm(BaseModel):
    character_id: int
    rows: list[CharacterRoutineRow]


def _has_routine(character: Character, time: Stamp) -> bool:
    return any((row.start is None or row.start <= time) and (row.end is None or row.end > time) for row in character.routines)


def _residents(s: Session, places: list[DayPlace], time: Stamp) -> list[Character]:
    ids = {place.id for place in places}
    characters = s.scalars(
        world_creation_query.alive_characters_select(time)
        .where(Character.locations.any(CharacterLocation.location_id.in_(ids)))
        .order_by(Character.id)).all()
    return [character for character in characters if _current_location_id(character, time) in ids]


def _time(s: Session, form: RoutineForm) -> Stamp:
    if form.time is not None:
        return form.time
    first = (form.character_ids or [form.around_character_id])[0]
    if first is None:
        raise ValueError("人物を渡す(character_ids か around_character_id)")
    last = expansion_query.last_appearance(s, first)
    if last is None:
        raise ValueError(f"人物 id={first} の出た時刻が分からない。time を渡す")
    return last


def _material(s: Session, character: Character, time: Stamp) -> RoutineCharacter | str:
    """材料か、決められないわけ。"""
    if _has_routine(character, time):
        return "決まった居場所の行がもうある"
    location_id = _current_location_id(character, time)
    if location_id is None:
        return "その時刻の居場所が分からない"
    location = s.get_one(Location, location_id)
    area = area_of(s, location)
    if area is None:
        return f"住まいの「{location.name}」が詳細の場所でない"
    places = places_of(s, area, time)
    home = next((place for place in places if place.id == location.id),
                DayPlace(id=location.id, name=location.name, kind=location.kind))
    histories = sorted((row for row in character.histories if row.start is None or row.start <= time),
                       key=lambda row: (row.start is not None, row.start or time, row.id))
    relations = [f"{line.character_2.name if line.character_1.id == character.id else line.character_1.name}: {line.relation}"
                 for line in relations_at(s, [character], time, dated_alive_at)]
    calendar = active_calendar()
    return RoutineCharacter(
        character_id=character.id, name=character.name, age=age_at(character, time), text=character.text,
        principle=character.principle,
        histories=[row.description for row in histories][-constants.ROUTINE_HISTORY_LIMIT:],
        relations=relations, home=home, places=places, hours_per_day=24 if calendar is None else calendar.hours_per_day)


def routine_targets(s: Session, form: RoutineForm) -> RoutineTargets:
    """名指しした人物と、`around_character_id` のエリアに住む人物のうち、決まった居場所の行の無い人物の材料
    (`ROUTINE_DRAFT_LIMIT` 人まで。ほかはわけを添えて外す)。"""
    time = _time(s, form)
    characters = [common_query.get_row(s, Character, id_) for id_ in dict.fromkeys(form.character_ids)]
    if form.around_character_id is not None:
        center = common_query.get_row(s, Character, form.around_character_id)
        location_id = _current_location_id(center, time)
        area = None if location_id is None else area_of(s, s.get_one(Location, location_id))
        if area is None:
            raise ValueError(f"{center.name}(id={center.id})の居場所が詳細の場所でないので、周りの人物を決められない")
        # 周りを見る中心の人物はふつう動かす側なので、名指ししたときだけ決める
        known = {character.id for character in characters} | {center.id}
        characters += [character for character in _residents(s, places_of(s, area, time), time)
                       if character.id not in known]
    targets: list[RoutineCharacter] = []
    skipped: list[RoutineSkipped] = []
    for character in characters:
        found = _material(s, character, time)
        if isinstance(found, str):
            skipped.append(RoutineSkipped(character_id=character.id, name=character.name, reason=found))
        elif len(targets) >= constants.ROUTINE_DRAFT_LIMIT:
            skipped.append(RoutineSkipped(character_id=character.id, name=character.name,
                                          reason=f"一度に {constants.ROUTINE_DRAFT_LIMIT} 人まで"))
        else:
            targets.append(found)
    return RoutineTargets(time=time, characters=targets, skipped=skipped)


def _hours(period: str, hours_per_day: int) -> tuple[int, int]:
    start, end = constants.ROUTINE_PERIODS[period]
    # 半端は切り上げる(30 時の暦の 6 時は 7.5 時で、8 時から)
    return (math.floor(start * hours_per_day / 24 + 0.5) % hours_per_day,
            math.floor(end * hours_per_day / 24 + 0.5) % hours_per_day)


def usable_rows(draft: RoutineDraft, character: RoutineCharacter) -> list[CharacterRoutineRow]:
    """時間帯ごとに一つ(先の行)を、時間帯の順に暦の時へ割り直す。続く時間帯で場所としていることが同じなら一行にまとめる。
    行ける場所の外・時間帯の外・していることの空な行は外す。"""
    place_ids = {place.id for place in character.places}
    by_period: dict[str, RoutineDraftRow] = {}
    for row in draft.routines:
        if row.period in constants.ROUTINE_PERIODS and row.location_id in place_ids and row.text.strip():
            by_period.setdefault(row.period, row)
    rows: list[CharacterRoutineRow] = []
    last: RoutineDraftRow | None = None
    for period in constants.ROUTINE_PERIODS:
        row = by_period.get(period)
        if row is None:
            last = None
            continue
        hour_from, hour_to = _hours(period, character.hours_per_day)
        if last is not None and (last.location_id, last.text.strip()) == (row.location_id, row.text.strip()):
            rows[-1].hour_to = hour_to
        else:
            rows.append(CharacterRoutineRow(location_id=row.location_id, hour_from=hour_from, hour_to=hour_to,
                                            text=row.text.strip()))
        last = row
    return rows


def add_routines(s: Session, form: RoutineAddForm) -> list[CharacterRoutineRow]:
    common_query.get_row(s, Character, form.character_id)
    added = [CharacterRoutine(character_id=form.character_id, location_id=row.location_id, hour_from=row.hour_from,
                              hour_to=row.hour_to, text=row.text, start=row.start, end=row.end) for row in form.rows]
    s.add_all(added)
    s.flush()
    return [CharacterRoutineRow.model_validate(row) for row in s.scalars(
        select(CharacterRoutine).where(CharacterRoutine.id.in_([row.id for row in added]))
        .order_by(CharacterRoutine.id)).all()]


class DraftedRoutines(BaseModel):
    character_id: int
    name: str | None = None
    routines: list[CharacterRoutineRow]


class RoutineRun(BaseModel):
    """`DraftRoutines` のレスポンス。"""

    time: Timestamp
    drafted: list[DraftedRoutines] = []
    # 決まって通う所が無いと AI が決めた人物
    none: list[RoutineSkipped] = []
    skipped: list[RoutineSkipped] = []
