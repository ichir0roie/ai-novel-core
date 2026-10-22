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


def outfit_at(s: Session, character: Character, time: Stamp) -> list[str]:
    """時刻に身に着けている物ごとに、効いている来歴の行のうち一番新しい行の文。身に着けた順。"""
    worn = [rows for skill in skills_of(s, character.id) if skill.kind == OUTFIT_KIND and (rows := rows_at(skill, time))]
    return [rows[-1].description for rows in sorted(worn, key=lambda rows: by_start(rows[0]))]
