from sqlalchemy.orm import Session, joinedload

from ai.instructions.event_writing import RECENT_EVENT_LIMIT
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.models import CastSerialized, ParticipantSerialized
from data_access_logic.character.parameters import parameters_at
from data_access_logic.event.summary import summarized_events
from data_access_logic.query import common_query
from db.schema import Character, CharacterRelation, ConfirmStatus, Event
from db.stamp import Stamp


def age_at(character: Character, time: Stamp) -> int | None:
    if character.start is None:
        return None
    born = character.start
    return time.year - born.year - ((time.month, time.day) < (born.month, born.day))


def _relations(s: Session, character: Character, time: Stamp) -> list[CharacterRelation]:
    return list(s.scalars(
        common_query.character_relations_at_select(character.id, time)
        .limit(constants.RELATION_LIMIT)
        .options(joinedload(CharacterRelation.character_1), joinedload(CharacterRelation.character_2))
        .execution_options(populate_existing=True)
    ).all())


def cast_at(s: Session, ai: AIClient, characters: list[Character], time: Stamp) -> list[CastSerialized]:
    """話に使うのは、ユーザが確かめた(`confirmed=承認`)出来事だけ。"""
    cast = []
    for character in characters:
        recent_events = summarized_events(
            s, ai,
            common_query.events_of_character_select(
                character.id, until=time, limit=constants.EPISODE_CHARACTER_EVENT_LIMIT)
            .where(Event.confirmed == ConfirmStatus.APPROVED))
        cast.append(CastSerialized(
            character=character,
            age=age_at(character, time),
            parameters=parameters_at(character, time),
            relations=_relations(s, character, time),
            recent_events=list(reversed(recent_events)),
        ))
    return cast


def participants_at(s: Session, characters: list[Character], time: Stamp) -> list[ParticipantSerialized]:
    return [
        ParticipantSerialized(
            character=character,
            age=age_at(character, time),
            parameters=parameters_at(character, time),
            relations=_relations(s, character, time),
            recent_events=s.scalars(
                common_query.events_of_character_select(character.id, until=time, limit=RECENT_EVENT_LIMIT)
            ).all(),
        )
        for character in characters
    ]

