from sqlalchemy import Select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.character.models import (
    CastCandidateSerialized, CastSerialized, CharacterHistoryMaterial, CharacterRelationLine, CharacterSecrets,
    CharacterSkillMaterial, MentionedSerialized, ParticipantSerialized,
)
from data_access_logic.character.histories import histories_at, rows_at
from data_access_logic.character.parameters import parameters_at
from data_access_logic.character import skills
from data_access_logic.event.summary import events_of
from data_access_logic.knowers import knowers_at
from data_access_logic.query import common_query
from db.schema import Character, CharacterHistory, CharacterSkillHistory, Event
from db.stamp import Stamp


def age_at(character: Character, time: Stamp) -> int | None:
    if character.start is None:
        return None
    born = character.start
    return time.year - born.year - ((time.month, time.day) < (born.month, born.day))


def relations_at(s: Session, characters: list[Character], time: Stamp) -> list[CharacterRelationLine]:
    """`time` に続いている関係を、`time` の年までに起きた来歴だけを付けて返す。

    関係の芯(`text`)は時期を限らないので、先のことは来歴の行に書けば、それより前の話・人物役には渡らない。
    """
    rows = s.scalars(common_query.character_relations_at_select([character.id for character in characters], time)).all()
    return [
        CharacterRelationLine(
            character_1=row.character_1, character_2=row.character_2, relation=row.relation, text=row.text,
            histories=sorted((history for history in row.histories if history.covers(time)),
                             key=lambda history: history.start or 0))
        for row in rows
    ]


def _recent_events_select(character: Character, time: Stamp) -> Select[Event]:
    return common_query.events_of_character_select(character.id, until=time, limit=constants.EPISODE_CHARACTER_EVENT_LIMIT)


def cast_event_ids(s: Session, characters: list[Character], time: Stamp) -> list[int]:
    """`cast_of` が要約で渡す出来事(要約を揃えておく出来事)。"""
    return [event.id for character in characters for event in s.scalars(_recent_events_select(character, time)).all()]


def cast_of(s: Session, characters: list[Character], time: Stamp) -> list[CastSerialized]:
    """出来事の要約はそのときのまま読む(作り直さない)。"""
    return [
        CastSerialized(
            character=character,
            age=age_at(character, time),
            parameters=parameters_at(character, time),
            histories=histories_at(character, time),
            recent_events=list(reversed(events_of(s, _recent_events_select(character, time)))),
        )
        for character in characters
    ]


def _history_material(s: Session, row: CharacterHistory | CharacterSkillHistory, time: Stamp) -> CharacterHistoryMaterial:
    return CharacterHistoryMaterial(start=row.start, description=row.description, knowers=knowers_at(s, row.knowers, time))


def secrets_at(s: Session, character: Character, time: Stamp) -> CharacterSecrets:
    skill_rows = [(skill, skills.rows_at(skill, time)) for skill in skills.skills_of(s, character.id)]
    return CharacterSecrets(
        histories=[_history_material(s, row, time) for row in rows_at(character, time)],
        skills=[CharacterSkillMaterial(name=skill.name, text=skill.text,
                                       histories=[_history_material(s, row, time) for row in rows])
                for skill, rows in skill_rows if rows],
    )


def mentioned_of(characters: list[Character], time: Stamp) -> list[MentionedSerialized]:
    return [
        MentionedSerialized(character=character, age=age_at(character, time), parameters=parameters_at(character, time),
                            histories=histories_at(character, time))
        for character in characters
    ]


def candidate_at(character: Character, time: Stamp) -> CastCandidateSerialized:
    return CastCandidateSerialized(character=character, age=age_at(character, time), parameters=parameters_at(character, time),
                                   histories=histories_at(character, time))


def participants_at(s: Session, characters: list[Character], time: Stamp) -> list[ParticipantSerialized]:
    return [
        ParticipantSerialized(
            character=character,
            age=age_at(character, time),
            parameters=parameters_at(character, time),
            histories=histories_at(character, time),
            relations=relations_at(s, [character], time),
            recent_events=s.scalars(
                common_query.events_of_character_select(character.id, until=time, limit=constants.RECENT_EVENT_LIMIT)
            ).all(),
        )
        for character in characters
    ]

