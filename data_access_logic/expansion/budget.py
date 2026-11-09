"""人物モードのリソース制限。動機づけ(気力)・行動量(手数)・影響量(影響の枠)を、db に列を足さずに記録から数える。

- 気力: 行動力の段で上限が決まり、自分から一手を打つと `ACT_COST_ACT`、ほかの人物の一手で出来事の当事者になると
  `ACT_COST_INVOLVED` 減る。`ACT_ENERGY_RECOVERY_DAYS` 日ごとに 1 戻る。数えるのは終えた展開(done)だけ(取り消した手は戻る)
- 手数: `ACT_WINDOW_DAYS` 日のあいだに自分から打てる手は `ACT_WINDOW_LIMIT` まで
- 影響の枠: 動いた人物の影響力(主要人物は `MAIN_CHARACTER_MIN_INFLUENCE` より下に扱わない)で幅が決まり、成り行きが悪ければ一段狭まる。
  動いた人物より影響力が上の人物は、その一手では人となりの変化(モチベーションの増減を含む)・住まいの移動を書かれない
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.character.parameters import parameters_at
from data_access_logic.expansion.act_models import ActOutcomeDraft, ImpactFrame
from db.schema import ChangeOp, Character, Event, EventCharacter, Expansion, ExpansionChange, ExpansionMode, ExpansionStatus
from db.stamp import Stamp

_LEVELS = list(constants.LEVEL_RANKS)


def rank(level: str) -> int:
    return constants.LEVEL_RANKS.get(level, constants.LEVEL_RANKS["並"])


def influence_of(character: Character, time: Stamp) -> str:
    level = parameters_at(character, time).influence or "並"
    floor = constants.MAIN_CHARACTER_MIN_INFLUENCE
    return floor if character.main_character and rank(level) < rank(floor) else level


def _own_act_times(s: Session, character_id: int, until: Stamp) -> list[Stamp]:
    return [time for time in s.scalars(
        select(Expansion.time).where(
            Expansion.mode == ExpansionMode.CHARACTER, Expansion.status == ExpansionStatus.DONE,
            Expansion.actor_id == character_id, Expansion.time <= until)).all() if time is not None]


def _involved_times(s: Session, character_id: int, until: Stamp) -> list[Stamp]:
    """ほかの人物の一手が足した出来事のうち、この人物が当事者のものの時刻。"""
    added_by_others = (
        select(ExpansionChange.row_id).join(Expansion, Expansion.id == ExpansionChange.expansion_id)
        .where(Expansion.mode == ExpansionMode.CHARACTER, Expansion.status == ExpansionStatus.DONE,
               Expansion.actor_id != character_id, ExpansionChange.table_name == Event.__tablename__,
               ExpansionChange.op == ChangeOp.ADD))
    return [time for time in s.scalars(
        select(Event.time).where(
            Event.id.in_(added_by_others), Event.time <= until,
            Event.event_characters.any(EventCharacter.character_id == character_id))).all() if time is not None]


def energy_max(character: Character, time: Stamp) -> int:
    return constants.ACT_ENERGY_MAX.get(parameters_at(character, time).proactivity or "並", 0)


def energy_at(s: Session, character: Character, time: Stamp) -> float:
    """`time` の気力。使った時刻を古い順にたどり、あいだの日数ぶん戻してから減らす。"""
    maximum = float(energy_max(character, time))
    spent = sorted([(at, constants.ACT_COST_ACT) for at in _own_act_times(s, character.id, time)]
                   + [(at, constants.ACT_COST_INVOLVED) for at in _involved_times(s, character.id, time)],
                   key=lambda pair: pair[0])
    energy, last = maximum, None
    for at, cost in spent:
        if last is not None:
            energy = min(maximum, energy + last.days_until(at) / constants.ACT_ENERGY_RECOVERY_DAYS)
        energy -= cost
        last = at
    if last is not None:
        energy = min(maximum, energy + last.days_until(time) / constants.ACT_ENERGY_RECOVERY_DAYS)
    return energy


def acts_in_window(s: Session, character_id: int, time: Stamp) -> int:
    since = time.plus_days(-constants.ACT_WINDOW_DAYS)
    return sum(1 for at in _own_act_times(s, character_id, time) if since < at)


def can_act(s: Session, character: Character, time: Stamp) -> bool:
    return (energy_at(s, character, time) >= constants.ACT_COST_ACT
            and acts_in_window(s, character.id, time) < constants.ACT_WINDOW_LIMIT)


def ready_time(s: Session, character: Character, time: Stamp) -> Stamp | None:
    """`time` 以降で、気力と手数が足りて一手を打てる一番早い日。行動力が無なら None。"""
    if energy_max(character, time) < constants.ACT_COST_ACT:
        return None
    at = time
    # 気力は ACT_ENERGY_RECOVERY_DAYS 日ごと、手数は ACT_WINDOW_DAYS 日で必ず空くので、日を進めればいずれ打てる
    for _ in range(constants.ACT_WINDOW_DAYS + constants.ACT_ENERGY_MAX["必"] * constants.ACT_ENERGY_RECOVERY_DAYS):
        if can_act(s, character, at):
            return at
        at = at.plus_days(1)
    return None


def can_be_involved(s: Session, character: Character, time: Stamp) -> bool:
    return energy_at(s, character, time) >= constants.ACT_COST_INVOLVED


def frame(s: Session, actor: Character, participants: list[Character], time: Stamp, roll: str) -> ImpactFrame:
    level = influence_of(actor, time)
    if roll in constants.ACT_NARROWING_OUTCOMES:
        level = _LEVELS[max(rank(level) - 1, 0)]
    actor_rank = rank(influence_of(actor, time))
    resistant = [other for other in participants
                 if other.id != actor.id and rank(influence_of(other, time)) > actor_rank]
    return ImpactFrame(
        influence=influence_of(actor, time), people=constants.ACT_IMPACT_PEOPLE[level],
        moves=constants.ACT_IMPACT_MOVES[level],
        new_characters=min(constants.ACT_IMPACT_NEW_CHARACTERS[level], constants.ACT_NEW_CHARACTER_LIMIT),
        ideas=min(constants.ACT_IMPACT_IDEAS[level], constants.ACT_NEW_IDEA_LIMIT),
        location_change=rank(level) >= rank(constants.ACT_IMPACT_LOCATION_MIN),
        resistant_ids=[other.id for other in resistant], resistant_names=[other.name or "" for other in resistant])


def clamp(outcome: ActOutcomeDraft, impact: ImpactFrame, actor_id: int) -> ActOutcomeDraft:
    """裁いた結果のうち、影響の枠をはみ出た分を切る。動いた人物の分は先に残す。"""
    resistant = set(impact.resistant_ids)

    def first_actor[T](rows: list[T], key) -> list[T]:
        return sorted(rows, key=lambda row: key(row) != actor_id)

    updates = [update for update in first_actor(outcome.character_updates, lambda row: row.character_id)
               if update.character_id not in resistant][:impact.people]
    moves = [move for move in first_actor(outcome.character_moves, lambda row: row.character_id)
             if move.character_id not in resistant][:impact.moves]
    # 思いの増減も人となりの変化に数え、動かされにくい人物の分は書かない
    motivation_changes = [change for change in first_actor(outcome.motivation_changes, lambda row: row.character_id)
                          if change.character_id not in resistant][:constants.ACT_MOTIVATION_CHANGE_LIMIT]
    return outcome.model_copy(update={
        "character_updates": updates, "character_moves": moves, "motivation_changes": motivation_changes,
        "location_abolished": outcome.location_abolished and impact.location_change,
        "location_founded": outcome.location_founded if impact.location_change else None,
        "new_characters": outcome.new_characters[:impact.new_characters],
        "ideas": outcome.ideas[:impact.ideas],
    })
