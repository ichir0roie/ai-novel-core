#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from pydantic import Field, computed_field, model_serializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.character.reading import CharacterSheet, character_sheet, residents
from data_access_logic.episode.reading import EpisodeTitle
from data_access_logic.event.reading import EventRow
from data_access_logic.idea.alias import called
from data_access_logic.location.models import LocationMaterial
from data_access_logic.location.record import LocationRecord
from data_access_logic.material import Material, Named, Timestamp
from data_access_logic.query import common_query
from data_access_logic.story.record import StoryRecord
from db.schema import Character, Event, Idea, IdeaRecognition, Location, Story
from db.stamp import Stamp


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
    path: list[LocationMaterial]
    time: Timestamp
    reach: int
    open_events: list[EventRow]
    recent_events: list[EventRow]
    ideas: list[BriefIdea]
    present_characters: list[Named]


class CastScope(Named):
    path: list[LocationMaterial]


class Cast(Material):
    story: Named
    time: Timestamp
    scope: CastScope
    characters: list[CharacterSheet]


def story_digest(s: Session, story: Story) -> StoryDigest:
    episodes = s.scalars(common_query.story_episodes_select(story.id)).all()
    return StoryDigest(
        story=_StoryWithPlaces.model_validate(story),
        episode_count=len(episodes),
        last_episode=EpisodeTitle.model_validate(episodes[-1]) if episodes else None,
        unsynced=[EpisodeTitle.model_validate(episode) for episode in episodes if not episode.synced],
    )


def stories(s: Session) -> list[StoryDigest]:
    rows = s.scalars(common_query.stories_select()).all()
    return [story_digest(s, story) for story in rows]


def brief(s: Session, place_id: int, when: Stamp | str | None = None, reach: int = 60, full: bool = False) -> Brief:
    location = common_query.get_row(s, Location, place_id)
    if when is None:
        raise ValueError("時刻が決まらない(when を渡す)")
    since, until = common_query.span(when)
    place_ids = common_query.descendant_place_ids(s, place_id)

    def visible(events: list[Event]) -> list[EventRow]:
        return [EventRow.model_validate(event) for event in events if full or not event.hidden]

    recent_query = (select(Event)
                    .options(*common_query.EVENT_LOAD_OPTIONS)
                    .where(Event.location_id.in_(place_ids),
                           Event.time <= until,
                           Event.time >= Stamp(max(1, since.year - reach)))
                    .order_by(Event.time.desc(), Event.id.desc()))
    recent = list(s.scalars(recent_query).all())

    character_ids = residents(s, place_ids, until)
    ideas = s.scalars(
        common_query.ideas_select(common_query.idea_scope_ids(s, place_id), until)).all()
    recognitions = called(s, [idea.id for idea in ideas], place_id, until)

    characters = s.scalars(select(Character).where(Character.id.in_(character_ids))).all() if character_ids else []
    character_names = {character.id: character.name for character in characters}

    return Brief(
        place=LocationRecord.model_validate(location),
        path=common_query.place_path(s, place_id),
        time=until,
        reach=reach,
        open_events=visible(list(s.scalars(common_query.open_events_select(place_ids, until)).all())),
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


def cast(s: Session, story_id: int, when: Stamp | str | None = None, count: int = 5, levels: int = 1) -> Cast:
    story = common_query.get_row(s, Story, story_id)
    if story.place_id is None:
        raise ValueError(f"作品 {story.name} に立つ場所(place_id)が無い")
    _, until = common_query.resolve_time(s, when, story)
    root_id = common_query.place_up(s, story.place_id, levels)
    root = s.get_one(Location, root_id)
    place_ids = common_query.descendant_place_ids(s, root_id)
    character_ids = residents(s, place_ids, until)
    return Cast(
        story=Named.model_validate(story),
        time=until,
        scope=CastScope(id=root.id, name=root.name, path=common_query.place_path(s, root_id)),
        characters=[character_sheet(s, id_, until=until, count=count, text=False) for id_ in character_ids],
    )
