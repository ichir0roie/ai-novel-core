#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from pydantic import Field, SerializeAsAny, computed_field, model_serializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.character.record import CharacterHead, CharacterRecord
from data_access_logic.episode.record import EpisodeHead, EpisodeRow
from data_access_logic.event.record import EventColumns
from data_access_logic.idea.alias import called
from data_access_logic.location.record import LocationRecord
from data_access_logic.material import Material, Timestamp
from data_access_logic.query import common_query
from data_access_logic.story.record import StoryRecord
from db.schema import Character, Event, Idea, IdeaRecognition, Location, Story
from db.stamp import Stamp


class Named(Material):
    id: int
    name: str | None = None


class PathStep(Material):
    id: int
    name: str | None = None
    kind: str | None = None


class _EventCharacter(Material):
    character_id: int
    character: Named | None = None


class EventRowHead(EventColumns):
    location: Named | None = Field(default=None, exclude=True)
    event_characters: list[_EventCharacter] = Field(exclude=True)

    @computed_field
    @property
    def place_name(self) -> str | None:
        return None if self.location is None else self.location.name

    @computed_field
    @property
    def characters(self) -> list[Named]:
        return [Named(id=link.character_id, name=None if link.character is None else link.character.name)
                for link in self.event_characters]


class EventRow(EventRowHead):
    text: str


class PlaceAt(Material):
    place_id: int
    place_name: str | None = None
    start: Timestamp | None = None


class CharacterSheet(Material):
    """人物の列に、ある時刻の名字・体格・口調・性格(`parameters_at`)を同じ段に並べて出す。"""

    character: SerializeAsAny[CharacterHead]
    parameters_at: CharacterParameterValues
    place: PlaceAt | None = None
    recent_events: list[SerializeAsAny[EventRowHead]]

    @model_serializer(mode="wrap")
    def _flat(self, handler: Any) -> dict:
        data = handler(self)
        return {**data.pop("character"), **data.pop("parameters_at"), **data}


class EpisodeTitle(Material):
    id: int
    start: Timestamp | None = None
    title: str


class UnsyncedEpisode(EpisodeTitle):
    story_id: int
    story: Named | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def story_name(self) -> str | None:
        return None if self.story is None else self.story.name


class _StoryWithPlaces(StoryRecord):
    world: Named | None = Field(default=None, exclude=True)
    place: Named | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def world_name(self) -> str | None:
        return None if self.world is None else self.world.name

    @computed_field
    @property
    def place_name(self) -> str | None:
        return None if self.place is None else self.place.name


class StoryDigest(Material):
    """作品の列に、話の数・最後の話・未同期の話を同じ段に並べて出す。"""

    story: _StoryWithPlaces
    episode_count: int
    last_episode: EpisodeTitle | None = None
    unsynced: list[EpisodeTitle]

    @model_serializer(mode="wrap")
    def _flat(self, handler: Any) -> dict:
        data = handler(self)
        return {**data.pop("story"), **data}


class BriefIdea(Material):
    id: int
    name: str
    kind: str
    text: str | None = None


class Brief(Material):
    place: LocationRecord
    path: list[PathStep]
    time: Timestamp
    reach: int
    open_events: list[EventRow]
    recent_events: list[EventRow]
    ideas: list[BriefIdea]
    present_characters: list[Named]


class CastScope(Named):
    path: list[PathStep]


class Cast(Material):
    story: Named
    time: Timestamp
    scope: CastScope
    characters: list[CharacterSheet]


def event_row(event: Event, text: bool = True) -> EventRowHead:
    return (EventRow if text else EventRowHead).model_validate(event)


def events_at(session: Session, when, place_ids=None, limit=None, text: bool = True) -> list[EventRowHead]:
    rows = session.scalars(
        common_query.events_at_select(when, place_ids=place_ids, limit=limit)).all()
    return [event_row(row, text=text) for row in rows]


def events_of(session: Session, select_fn, record_id: int, until=None, limit=5,
              text: bool = True) -> list[EventRowHead]:
    rows = session.scalars(select_fn(record_id, until=until, limit=limit)).all()
    return [event_row(row, text=text) for row in rows]


def residents(session: Session, place_ids, until: Stamp) -> list[int]:
    character_ids = session.scalars(
        common_query.resident_character_ids_select(place_ids, until)).all()
    return [id_ for id_ in character_ids if id_ is not None]


def path_of(session: Session, place_id: int) -> list[PathStep]:
    return [PathStep.model_validate(step) for step in common_query.place_path(session, place_id)]


def _place_at(session: Session, character_id: int, until: Stamp) -> PlaceAt | None:
    row = session.scalars(common_query.character_place_select(character_id, until)).first()
    if row is None:
        return None
    return PlaceAt(place_id=row.location_id, place_name=row.place.name if row.place else None, start=row.start)


def character_sheet(session: Session, character_id: int, until=None,
                    count: int = 5, text: bool = True) -> CharacterSheet:
    character = session.scalars(common_query.character_select(character_id)).first()
    if character is None:
        raise common_query.NotFoundError(f"character_id={character_id} という id の character が見つからない")
    at = common_query.span(until)[1] if until is not None else Stamp(99999, 12, 31, 23, 59, 59)

    return CharacterSheet(
        character=(CharacterRecord if text else CharacterHead).model_validate(character),
        # 時刻を渡さないときは、期間を限らない値だけを重ねる
        parameters_at=CharacterParameterValues.model_validate(character.parameters_at(None if until is None else at)),
        place=_place_at(session, character_id, at),
        recent_events=events_of(
            session, common_query.events_of_character_select, character_id, until=None if until is None else at,
            limit=count, text=text),
    )


def story_digest(session: Session, story: Story) -> StoryDigest:
    episodes = session.scalars(common_query.story_episodes_select(story.id)).all()
    return StoryDigest(
        story=_StoryWithPlaces.model_validate(story),
        episode_count=len(episodes),
        last_episode=EpisodeTitle.model_validate(episodes[-1]) if episodes else None,
        unsynced=[EpisodeTitle.model_validate(episode) for episode in episodes if not episode.synced],
    )


def stories(session: Session) -> list[StoryDigest]:
    rows = session.scalars(common_query.stories_select()).all()
    return [story_digest(session, story) for story in rows]


def episodes(session: Session, story_id: int, count: int = 10, before=None,
             text: bool = True) -> list[EpisodeHead]:
    common_query._get(session, Story, story_id, "story_id")
    rows = session.scalars(
        common_query.episodes_select(story_id, count=count, before=before)).all()
    return [(EpisodeRow if text else EpisodeHead).model_validate(episode) for episode in reversed(rows)]


def unsynced_episodes(session: Session, story_id: int | None = None) -> list[UnsyncedEpisode]:
    rows = session.scalars(common_query.unsynced_episodes_select(story_id)).all()
    return [UnsyncedEpisode.model_validate(episode) for episode in rows]


def brief(session: Session, place_id: int, when=None, reach: int = 60, full: bool = False) -> Brief:
    location = common_query._get(session, Location, place_id, "place_id")
    if when is None:
        raise ValueError("時刻が決まらない(when を渡す)")
    since, until = common_query.span(when)
    place_ids = common_query.descendant_place_ids(session, place_id)

    def visible(events: list[Event]) -> list[EventRow]:
        return [EventRow.model_validate(event) for event in events if full or not event.hidden]

    recent_query = (select(Event)
                    .options(*common_query.EVENT_LOAD_OPTIONS)
                    .where(Event.location_id.in_(place_ids),
                           Event.time <= until,
                           Event.time >= Stamp(max(1, since.year - reach)))
                    .order_by(Event.time.desc(), Event.id.desc()))
    recent = list(session.scalars(recent_query).all())

    character_ids = residents(session, place_ids, until)
    ideas = session.scalars(
        common_query.ideas_select(common_query.idea_scope_ids(session, place_id), until)).all()
    recognitions = called(session, [idea.id for idea in ideas], place_id, until)

    characters = session.scalars(select(Character).where(Character.id.in_(character_ids))).all() if character_ids else []
    character_names = {character.id: character.name for character in characters}

    return Brief(
        place=LocationRecord.model_validate(location),
        path=path_of(session, place_id),
        time=until,
        reach=reach,
        open_events=visible(list(session.scalars(common_query.open_events_select(place_ids, until)).all())),
        recent_events=visible(recent),
        ideas=[_brief_idea(idea, recognitions.get(idea.id)) for idea in ideas],
        present_characters=[Named(id=id_, name=character_names[id_]) for id_ in character_ids],
    )


def _brief_idea(idea: Idea, recognition: IdeaRecognition | None) -> BriefIdea:
    """その場所・時代の呼び名があればその名で、作中での受け止め方を本質の本文の前に置く。"""
    if recognition is None:
        return BriefIdea(id=idea.id, name=idea.name, kind=idea.kind, text=idea.text)
    return BriefIdea(id=idea.id, name=recognition.name, kind=idea.kind,
                     text=" ".join(part for part in (recognition.detail, idea.text) if part))


def cast(session: Session, story_id: int, when=None, count: int = 5, levels: int = 1) -> Cast:
    story = common_query._get(session, Story, story_id, "story_id")
    if story.place_id is None:
        raise ValueError(f"作品 {story.name} に立つ場所(place_id)が無い")
    _, until = common_query.resolve_time(session, when, story)
    root_id = common_query.place_up(session, story.place_id, levels)
    root = session.get_one(Location, root_id)
    place_ids = common_query.descendant_place_ids(session, root_id)
    character_ids = residents(session, place_ids, until)
    return Cast(
        story=Named.model_validate(story),
        time=until,
        scope=CastScope(id=root.id, name=root.name, path=path_of(session, root_id)),
        characters=[character_sheet(session, id_, until=until, count=count, text=False) for id_ in character_ids],
    )
