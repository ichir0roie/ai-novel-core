"""人物のスキルは、スキルの行(`character_skill`)ごとに、年ごとの来歴の行(`character_skill_history`)を時刻で絞って読む。"""
from collections.abc import Sequence

from sqlalchemy.orm import Session

from data_access_logic.query import common_query
from db.schema import CharacterSkill, CharacterSkillHistory
from db.stamp import Stamp


def skills_of(s: Session, character_id: int) -> Sequence[CharacterSkill]:
    return s.scalars(common_query.character_skills_select(character_id)).all()


def rows_at(skill: CharacterSkill, time: Stamp) -> list[CharacterSkillHistory]:
    """時刻の年までに始まった行を、始まりの古い順に返す。空なら、その時刻にはまだ持っていないスキル。"""
    return sorted((row for row in skill.histories if row.covers(time)), key=lambda row: row.start or 0)
