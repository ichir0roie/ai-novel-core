"""人物モードの影響の枠。動いた人物の影響力(主要人物は `MAIN_CHARACTER_MIN_INFLUENCE` より下に扱わない)で、一日の記録が
世界を動かせる幅を決める。動いた人物より影響力が上の人物は、その一日では人となりの変化(モチベーションの増減を含む)・住まいの移動を書かれない。
"""
from __future__ import annotations

from data_access_logic import constants
from data_access_logic.character.parameters import parameters_at
from data_access_logic.expansion.act_models import DayOutcomeDraft, ImpactFrame
from db.schema import Character
from db.stamp import Stamp


def rank(level: str) -> int:
    return constants.LEVEL_RANKS.get(level, constants.LEVEL_RANKS["並"])


def influence_of(character: Character, time: Stamp) -> str:
    level = parameters_at(character, time).influence or "並"
    floor = constants.MAIN_CHARACTER_MIN_INFLUENCE
    return floor if character.main_character and rank(level) < rank(floor) else level


def frame(actor: Character, participants: list[Character], time: Stamp) -> ImpactFrame:
    level = influence_of(actor, time)
    resistant = [other for other in participants
                 if other.id != actor.id and rank(influence_of(other, time)) > rank(level)]
    return ImpactFrame(
        influence=level, people=constants.ACT_IMPACT_PEOPLE[level], moves=constants.ACT_IMPACT_MOVES[level],
        new_characters=min(constants.ACT_IMPACT_NEW_CHARACTERS[level], constants.ACT_NEW_CHARACTER_LIMIT),
        ideas=min(constants.ACT_IMPACT_IDEAS[level], constants.ACT_NEW_IDEA_LIMIT),
        resistant_ids=[other.id for other in resistant], resistant_names=[other.name or "" for other in resistant])


def clamp(outcome: DayOutcomeDraft, impact: ImpactFrame, actor_id: int) -> DayOutcomeDraft:
    """記録のうち、影響の枠をはみ出た分を切る。動いた人物の分は先に残す。"""
    resistant = set(impact.resistant_ids)

    def first_actor[T](rows: list[T], key) -> list[T]:
        return sorted(rows, key=lambda row: key(row) != actor_id)

    nuances = [change for change in first_actor(outcome.nuance_changes, lambda row: row.character_id)
               if change.character_id not in resistant][:impact.people]
    moves = [move for move in first_actor(outcome.character_moves, lambda row: row.character_id)
             if move.character_id not in resistant][:impact.moves]
    # 思いの増減も人となりの変化に数え、動かされにくい人物の分は書かない
    motivation_changes = [change for change in first_actor(outcome.motivation_changes, lambda row: row.character_id)
                          if change.character_id not in resistant][:constants.ACT_MOTIVATION_CHANGE_LIMIT]
    return outcome.model_copy(update={
        "nuance_changes": nuances, "character_moves": moves, "motivation_changes": motivation_changes,
        "new_characters": outcome.new_characters[:impact.new_characters], "ideas": outcome.ideas[:impact.ideas],
    })
