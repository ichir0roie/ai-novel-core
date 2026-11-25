"""人物モード(`SimulateDay`)の、体の欲と行動量の決まり。db にも AI にも触らない計算だけを置く。

- 欲の段: 食欲・睡眠欲・性欲は、人物の時期ごとのパラメーター(`character_parameter`)で決める。決めていなければ年齢で決める
- 眠り: 起きる・寝る時刻は計算で決める。並の睡眠欲なら 24 時に寝て 8 時に起きる(一日を 24 に割った刻みの割合。一日の長さが違う暦でもそろえる)。
  前の夜に眠った時刻から一晩に要る眠りの時間だけ眠り、前の日に足りなかった眠りは、睡眠欲の段に応じた割合だけ朝を遅らせ、夜を早めて取り戻す。
  強いモチベーションがあるとき・行動量に余裕があるときは、それぞれ一時間早く起き、一時間遅く寝る
- 空腹・人と触れ合いたい欲: 一時間ごとに段の強さで増え、食べる・触れ合うと 0 に戻る。前の日に満ち足りなかったぶん、強く増える
- 満ち足り方: その日に欲が `DAY_NEED_COMFORT` を超えていた度合いと、眠れた時間の割合で、0〜100 に数える
- 行動量: 一時間の重みは、その一時間にした行い(`DAY_DEED_WEIGHTS`)のうち一番重いもの。七日の和が、行動力で決まる上限に近づくほど休みがちになる
"""
from __future__ import annotations

from collections.abc import Sequence

from data_access_logic import constants
from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.expansion.act_models import NeedProfile, Needs

_SLEEP = "眠る"


def _scaled(hours_per_day: int, hours_of_24: float) -> int:
    """一日を 24 に割った刻みの時間を、その暦の一時間の数に直す。"""
    return round(hours_of_24 * hours_per_day / 24)


def levels_of(values: CharacterParameterValues, age: int | None) -> tuple[str, str, str]:
    """食欲・睡眠欲・性欲の段。パラメーターで決めていない欲は、年齢の段にする。"""
    by_age = constants.DAY_NEED_UNKNOWN_AGE if age is None else next(
        levels for limit, levels in constants.DAY_NEED_BY_AGE if age < limit)
    chosen = (values.appetite, values.sleep_drive, values.libido)
    return tuple(str(level) if level is not None else default for level, default in zip(chosen, by_age))  # type: ignore[return-value]


def sleep_plan(hours_per_day: int, sleep_drive: str, debt: int, prev_bed: int, eager: int) -> tuple[int, int, int]:
    """一晩に要る眠り・起きる時刻・寝る時刻(その日の一時間の番号)。`debt` は前の日に足りなかった眠りの時間、
    `prev_bed` は前の夜に眠った時刻、`eager` は早く起き遅く寝る時間(強いモチベーション・行動量の余裕)。"""
    required = max(1, round(_scaled(hours_per_day, constants.DAY_BASE_SLEEP_HOURS)
                            * constants.DAY_SLEEP_RATES[sleep_drive]))
    recover = min(_scaled(hours_per_day, constants.DAY_SLEEP_RECOVERY_MAX),
                  round(debt * constants.DAY_SLEEP_RECOVERY[sleep_drive]))
    wake = min(hours_per_day - 1, max(0, prev_bed + required + recover - eager))
    base_wake = _scaled(hours_per_day, constants.DAY_BASE_WAKE)
    bed = base_wake + hours_per_day - required - recover + eager
    return required, wake, max(wake + 1, bed)


def asleep_at(hour: int, profile: NeedProfile) -> bool:
    """規則で眠っている時間か。前の夜の眠りが朝まで続く時間と、その夜に眠ってから後。"""
    return profile.prev_bed <= hour < profile.wake or hour >= profile.bed


def sleepiness_at(hour: int, profile: NeedProfile) -> int:
    """起きてから寝るまでの、どこまで来たか(0〜100)。眠っている時間は 0。"""
    if asleep_at(hour, profile) or hour < profile.wake:
        return 0
    return min(100, round(100 * (hour - profile.wake) / max(1, profile.bed - profile.wake)))


def next_needs(needs: Needs, kind: str, hour: int, hours_per_day: int, profile: NeedProfile) -> Needs:
    """一時間を過ごしたあとの欲。空腹と人と触れ合いたい欲は段の強さ・前の日の不足で増え、食べる・触れ合うと 0 に戻る。
    増え方は一日 24 時間の暦の量で、一日の長さが違う暦では、一日あたりの量がそろうように割合を直す。"""
    scale = 24 / hours_per_day
    food = constants.DAY_HUNGER_PER_HOUR * constants.DAY_NEED_RATES[profile.appetite] * profile.food_pressure
    touch = constants.DAY_DESIRE_PER_HOUR * constants.DAY_NEED_RATES[profile.libido] * profile.touch_pressure
    # 眠っているあいだは、空腹もゆっくり増える
    if kind == _SLEEP:
        food /= 3
    hunger = 0 if kind == "食べる" else min(100, needs.hunger + round(food * scale))
    desire = 0 if kind == "触れ合う" else min(100, needs.desire + round(touch * scale))
    return Needs(hunger=hunger, desire=desire, sleepiness=sleepiness_at(hour + 1, profile))


def _discomfort(values: Sequence[int]) -> int:
    """欲が心地よい値を超えていた度合い(0〜100)。"""
    if not values:
        return 0
    over = [max(0, value - constants.DAY_NEED_COMFORT) for value in values]
    return min(100, round(sum(over) / len(over) * 100 / (100 - constants.DAY_NEED_COMFORT)))


def satisfaction(hungers: Sequence[int], desires: Sequence[int], slept: int, profile: NeedProfile) -> tuple[int, int, int]:
    """その日の食欲・睡眠欲・性欲の満ち足り方(0〜100)。`slept` はその日に眠った時間の数。性欲が無の人物は、いつも満ち足りている。"""
    food = 100 - _discomfort(hungers)
    sleep = min(100, round(100 * slept / max(1, profile.required_sleep)))
    touch = 100 if constants.DAY_NEED_RATES[profile.libido] == 0 else 100 - _discomfort(desires)
    return food, sleep, touch


def pressure(satisfied: int | None) -> float:
    """前の日の満ち足り方から、その日に欲が強く働く割合。前の日の記録が無ければ 1。"""
    return 1.0 if satisfied is None else 1 + constants.DAY_PRESSURE_GAIN * (100 - satisfied) / 100


def sleep_debt(satisfied: int | None, required: int) -> int:
    """前の日に足りなかった眠りの時間。"""
    return 0 if satisfied is None else round(required * (100 - satisfied) / 100)


def motivation_strength(total_shortage: int) -> int:
    """さかのぼった不足の和から、欲を満たしたいモチベーションの強さ(0 なら持たない)。"""
    return max((strength for floor, strength in constants.DAY_NEED_MOTIVATION_STEPS if total_shortage >= floor), default=0)


def hour_load(deeds: Sequence[str]) -> int:
    return max((constants.DAY_DEED_WEIGHTS[deed] for deed in deeds if deed in constants.DAY_DEED_WEIGHTS), default=0)


def load_max(proactivity: str) -> int:
    return constants.DAY_LOOKBACK_DAYS * constants.DAY_LOAD_PER_DAY[proactivity]


def fatigue(profile: NeedProfile, today: int) -> int:
    """七日の行動量の、上限に対する割合(百分率)。行動力が無の人物は、いつも上限にいる。"""
    if profile.load_max <= 0:
        return 100
    return round(100 * (profile.load_before + today) / profile.load_max)


def rest_chance(fatigue_percent: int) -> float:
    """人物の目に聞かずに休む見込み。上限の `DAY_REST_FROM_RATIO` を超えたところから上がり、上限で一番高くなる。"""
    ratio = fatigue_percent / 100
    span = 1 - constants.DAY_REST_FROM_RATIO
    return min(constants.DAY_REST_MAX_CHANCE, max(0.0, (ratio - constants.DAY_REST_FROM_RATIO) / span))
