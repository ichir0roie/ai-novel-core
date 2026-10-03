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
from db.schema import Character, Event, Idea, IdeaHistory, Location, Story
from db.stamp import Stamp


class _StoryWithLocations(StoryRecord):
    world: Named | None = Field(default=None, exclude=True)
    location: Named | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def world_name(self) -> str | None:
        return None if self.world is None else self.world.name

    @computed_field
    @property
    def location_name(self) -> str | None:
        return None if self.location is None else self.location.name


class StoryDigest(Material):
    """作品の列に、話の数・最後の話・未同期の話を同じ段に並べて出す。"""

    story: _StoryWithLocations
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
    location: LocationRecord
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
        story=_StoryWithLocations.model_validate(story),
        episode_count=len(episodes),
        last_episode=EpisodeTitle.model_validate(episodes[-1]) if episodes else None,
        unsynced=[EpisodeTitle.model_validate(episode) for episode in episodes if not episode.synced],
    )


def stories(s: Session) -> list[StoryDigest]:
    rows = s.scalars(common_query.stories_select()).all()
    return [story_digest(s, story) for story in rows]


def brief(s: Session, location_id: int, when: Stamp | str | None = None, reach: int = 60, full: bool = False) -> Brief:
    location = common_query.get_row(s, Location, location_id)
    if when is None:
        raise ValueError("時刻が決まらない(when を渡す)")
    since, until = common_query.span(when)
    location_ids = common_query.descendant_location_ids(s, location_id)

    def visible(events: list[Event]) -> list[EventRow]:
        return [EventRow.model_validate(event) for event in events if full or not event.hidden]

    recent_query = (select(Event)
                    .options(*common_query.EVENT_LOAD_OPTIONS)
                    .where(Event.location_id.in_(location_ids),
                           Event.time <= until,
                           Event.time >= Stamp(max(1, since.year - reach)))
                    .order_by(Event.time.desc(), Event.id.desc()))
    recent = list(s.scalars(recent_query).all())

    character_ids = residents(s, location_ids, until)
    ideas = s.scalars(
        common_query.ideas_select(common_query.idea_scope_ids(s, location_id), until)).all()
    histories = called(s, [idea.id for idea in ideas], location_id, until)

    characters = s.scalars(select(Character).where(Character.id.in_(character_ids))).all() if character_ids else []
    character_names = {character.id: character.name for character in characters}

    return Brief(
        location=LocationRecord.model_validate(location),
        path=common_query.location_path(s, location_id),
        time=until,
        reach=reach,
        open_events=visible(list(s.scalars(common_query.open_events_select(location_ids, until)).all())),
        recent_events=visible(recent),
        ideas=[_brief_idea(idea, histories.get(idea.id)) for idea in ideas],
        present_characters=[Named(id=id_, name=character_names[id_]) for id_ in character_ids],
    )


def _brief_idea(idea: Idea, history: IdeaHistory | None) -> BriefIdea:
    """その場所・時代の呼び名があればその名で、作中での受け止め方を本質の本文の前に置く。"""
    if history is None:
        return BriefIdea(id=idea.id, name=idea.name, kind=idea.kind, text=idea.text)
    return BriefIdea(id=idea.id, name=history.name, kind=idea.kind,
                     text=" ".join(part for part in (history.detail, idea.text) if part))


def cast(s: Session, story_id: int, when: Stamp | str | None = None, count: int = 5, levels: int = 1) -> Cast:
    story = common_query.get_row(s, Story, story_id)
    if story.location_id is None:
        raise ValueError(f"作品 {story.name} に立つ場所(location_id)が無い")
    _, until = common_query.resolve_time(s, when, story)
    root_id = common_query.location_up(s, story.location_id, levels)
    root = s.get_one(Location, root_id)
    location_ids = common_query.descendant_location_ids(s, root_id)
    character_ids = residents(s, location_ids, until)
    return Cast(
        story=Named.model_validate(story),
        time=until,
        scope=CastScope(id=root.id, name=root.name, path=common_query.location_path(s, root_id)),
        characters=[character_sheet(s, id_, until=until, count=count, text=False) for id_ in character_ids],
    )
