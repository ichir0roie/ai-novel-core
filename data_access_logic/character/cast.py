from sqlalchemy import Select
from sqlalchemy.orm import Session

from ai.instructions.event_writing import RECENT_EVENT_LIMIT
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.models import CastSerialized, CharacterRelationLine, ParticipantSerialized
from data_access_logic.character.parameters import parameters_at
from data_access_logic.event.summary import events_of, summarized_events
from data_access_logic.query import common_query
from db.schema import Character, ConfirmStatus, Event
from db.stamp import Stamp


def age_at(character: Character, time: Stamp) -> int | None:
    if character.start is None:
        return None
    born = character.start
    return time.year - born.year - ((time.month, time.day) < (born.month, born.day))


def relations_at(s: Session, characters: list[Character], time: Stamp) -> list[CharacterRelationLine]:
    rows = s.execute(common_query.character_relations_at_select([character.id for character in characters], time))
    return [CharacterRelationLine.model_validate(row) for row in rows]


def _recent_events_select(character: Character, time: Stamp) -> Select[Event]:
    # 話に使うのは、ユーザが確かめた(`confirmed=承認`)出来事だけ
    return (common_query.events_of_character_select(character.id, until=time, limit=constants.EPISODE_CHARACTER_EVENT_LIMIT)
            .where(Event.confirmed == ConfirmStatus.APPROVED))


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
            recent_events=list(reversed(events_of(s, _recent_events_select(character, time)))),
        )
        for character in characters
    ]


def cast_at(s: Session, ai: AIClient, characters: list[Character], time: Stamp) -> list[CastSerialized]:
    for character in characters:
        summarized_events(s, ai, _recent_events_select(character, time))
    return cast_of(s, characters, time)


def participants_at(s: Session, characters: list[Character], time: Stamp) -> list[ParticipantSerialized]:
    return [
        ParticipantSerialized(
            character=character,
            age=age_at(character, time),
            parameters=parameters_at(character, time),
            relations=relations_at(s, [character], time),
            recent_events=s.scalars(
                common_query.events_of_character_select(character.id, until=time, limit=RECENT_EVENT_LIMIT)
            ).all(),
        )
        for character in characters
    ]

