"""人物のスキルは、スキルの行(`character_skill`)ごとに、年ごとの来歴の行(`character_skill_history`)を時刻で絞って読む。"""
from collections.abc import Sequence

from sqlalchemy.orm import Session

from data_access_logic.history_start import by_start
from data_access_logic.query import common_query
from db.schema import Character, CharacterSkill, CharacterSkillHistory
from db.stamp import Stamp

# 装いのスキルの種別。装いは見た人にそのまま知れるので、その時刻に効く来歴の行は知る相手に関わらず見た目として渡す(`outfit_at`)
OUTFIT_KIND = "装い"


def skills_of(s: Session, character_id: int) -> Sequence[CharacterSkill]:
    return s.scalars(common_query.character_skills_select(character_id)).all()


def techniques_of(s: Session, character_id: int) -> list[CharacterSkill]:
    """装いでないスキル(技・術・技能)。"""
    return [skill for skill in skills_of(s, character_id) if skill.kind != OUTFIT_KIND]


def rows_at(skill: CharacterSkill, time: Stamp) -> list[CharacterSkillHistory]:
    """時刻までに始まり、まだ終わっていない行を、始まりの古い順に返す。空なら、その時刻には持っていないスキル。"""
    return sorted((row for row in skill.histories if row.covers(time)), key=by_start)


def worn_since(skill: CharacterSkill, rows: list[CharacterSkillHistory]) -> Stamp | None:
    """身に着け始めた時刻。効いている一番古い行から、前の行の終わりがその行の始まりに続いている限りさかのぼる
    (裾が焦げたなど、姿が移り変わっただけの行は同じ物の続き。一度外して着け直したなら、着け直した時から)。"""
    since = rows[0].start
    while since is not None:
        previous = next((row for row in skill.histories
                         if row.start is not None and row.start < since and row.end == since), None)
        if previous is None:
            break
        since = previous.start
    return since


def worn_at(s: Session, character: Character, time: Stamp) -> list[tuple[CharacterSkill, list[CharacterSkillHistory]]]:
    """時刻に身に着けている物ごとに、そのスキルと効いている来歴の行(始まりの古い順)。身に着けた順。"""
    worn = [(skill, rows) for skill in skills_of(s, character.id)
            if skill.kind == OUTFIT_KIND and (rows := rows_at(skill, time))]
    return sorted(worn, key=lambda item: by_start(item[1][0]))


def outfit_at(s: Session, character: Character, time: Stamp) -> list[str]:
    """時刻に身に着けている物ごとに、効いている来歴の行のうち一番新しい行の文。身に着けた順。"""
    return [rows[-1].description for _, rows in worn_at(s, character, time)]
