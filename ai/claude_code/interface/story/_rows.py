#!/usr/bin/env python3
from __future__ import annotations

from pydantic import field_serializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.idea.alias import called
from data_access_logic.material import Material
from data_access_logic.query import common_query
from db.schema import Character, Event, Idea, IdeaRecognition, Location, Story
from db.schema_pydantic import to_dict_with
from db.stamp import Stamp


class _Named(Material):
    id: int
    name: str | None = None


class _PlaceAt(Material):
    place_id: int
    place_name: str | None = None
    start: Stamp | None = None

    @field_serializer("start")
    def _start(self, value: Stamp | None) -> str | None:
        return None if value is None else str(value)


class _EpisodeHead(Material):
    id: int
    start: Stamp | None = None
    title: str

    @field_serializer("start")
    def _start(self, value: Stamp | None) -> str | None:
        return None if value is None else str(value)


class _UnsyncedEpisode(_EpisodeHead):
    story_id: int
    story_name: str | None = None


def event_row(event, *, text: bool = True) -> dict:
    return {
        **to_dict_with(event, relations=common_query.EVENT_RELATIONS, text=text),
        "characters": [
            _Named(id=link.character_id, name=link.character.name if link.character else None).model_dump()
            for link in event.event_characters],
    }


def events_at(session: Session, when, *, place_ids=None, limit=None,
              text: bool = True) -> list[dict]:
    rows = session.scalars(
        common_query.events_at_select(when, place_ids=place_ids, limit=limit)).all()
    return [event_row(row, text=text) for row in rows]


def events_of(session: Session, select_fn, record_id: int, *, until=None, limit=5,
              text: bool = True) -> list[dict]:
    rows = session.scalars(select_fn(record_id, until=until, limit=limit)).all()
    return [event_row(row, text=text) for row in rows]


def residents(session: Session, place_ids, until: Stamp) -> list[int]:
    character_ids = session.scalars(
        common_query.resident_character_ids_select(place_ids, until)).all()
    return [id_ for id_ in character_ids if id_ is not None]


def _place_at(session: Session, character_id: int, until: Stamp) -> dict | None:
    row = session.scalars(common_query.character_place_select(character_id, until)).first()
    if row is None:
        return None
    return _PlaceAt(place_id=row.location_id, place_name=row.place.name if row.place else None,
                    start=row.start).model_dump()


def character_sheet(session: Session, character_id: int, *, until=None,
                    count: int = 5, text: bool = True) -> dict:
    character = session.scalars(common_query.character_select(character_id)).first()
    if character is None:
        raise common_query.NotFoundError(f"character_id={character_id} という id の character が見つからない")
    at = common_query.span(until)[1] if until is not None else Stamp(99999, 12, 31, 23, 59, 59)

    return {
        **to_dict_with(character, text=text),
        # 時刻を渡さないときは、期間を限らない値だけを重ねる
        **character.parameters_at(None if until is None else at),
        "place": _place_at(session, character_id, at),
        "recent_events": events_of(
            session, common_query.events_of_character_select, character_id, until=None if until is None else at,
            limit=count, text=text),
    }


def story_digest(session: Session, story: Story) -> dict:
    episodes = session.scalars(common_query.story_episodes_select(story.id)).all()
    return {
        **to_dict_with(story, relations={"world": "world_name", "place": "place_name"}),
        "episode_count": len(episodes),
        "last_episode": _EpisodeHead.model_validate(episodes[-1]).model_dump() if episodes else None,
        "unsynced": [_EpisodeHead.model_validate(episode).model_dump() for episode in episodes if not episode.synced],
    }


def stories(session: Session) -> list[dict]:
    rows = session.scalars(common_query.stories_select()).all()
    return [story_digest(session, story) for story in rows]


def episode_row(episode, *, text: bool = True) -> dict:
    return to_dict_with(episode, text=text)


def episodes(session: Session, story_id: int, *, count: int = 10, before=None,
             text: bool = True) -> list[dict]:
    common_query._get(session, Story, story_id, "story_id")
    rows = session.scalars(
        common_query.episodes_select(story_id, count=count, before=before)).all()
    return [episode_row(episode, text=text) for episode in reversed(rows)]


def unsynced_episodes(session: Session, story_id: int | None = None) -> list[dict]:
    rows = session.scalars(common_query.unsynced_episodes_select(story_id)).all()
    return [_UnsyncedEpisode(id=episode.id, start=episode.start, title=episode.title, story_id=episode.story_id,
                             story_name=episode.story.name if episode.story else None).model_dump()
            for episode in rows]


def brief(session: Session, place_id: int, when=None, *, reach: int = 60,
          full: bool = False) -> dict:
    location = common_query._get(session, Location, place_id, "place_id")
    if when is None:
        raise ValueError("時刻が決まらない(when を渡す)")
    since, until = common_query.span(when)
    place_ids = common_query.descendant_place_ids(session, place_id)

    def visible(events: list[Event]) -> list[dict]:
        return [event_row(event) for event in events if full or not event.hidden]

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

    return {
        "place": to_dict_with(location),
        "path": common_query.place_path(session, place_id),
        "time": str(until),
        "reach": reach,
        "open_events": visible(list(session.scalars(common_query.open_events_select(place_ids, until)).all())),
        "recent_events": visible(recent),
        "ideas": [_idea_row(idea, recognitions.get(idea.id)) for idea in ideas],
        "present_characters": [_Named(id=id_, name=character_names[id_]).model_dump() for id_ in character_ids],
    }


def _idea_row(idea: Idea, recognition: IdeaRecognition | None) -> dict:
    """その場所・時代の呼び名があればその名で、作中での受け止め方を本質の本文の前に置く。"""
    if recognition is None:
        return {"id": idea.id, "name": idea.name, "kind": idea.kind, "text": idea.text}
    return {"id": idea.id, "name": recognition.name, "kind": idea.kind,
            "text": " ".join(part for part in (recognition.detail, idea.text) if part)}


def cast(session: Session, story_id: int, when=None, *, count: int = 5,
         levels: int = 1) -> dict:
    story = common_query._get(session, Story, story_id, "story_id")
    if story.place_id is None:
        raise ValueError(f"作品 {story.name} に立つ場所(place_id)が無い")
    _, until = common_query.resolve_time(session, when, story)
    root_id = common_query.place_up(session, story.place_id, levels)
    root = session.get_one(Location, root_id)
    place_ids = common_query.descendant_place_ids(session, root_id)
    character_ids = residents(session, place_ids, until)
    return {
        "story": {"id": story.id, "name": story.name},
        "time": str(until),
        "scope": {**_Named(id=root.id, name=root.name).model_dump(), "path": common_query.place_path(session, root_id)},
        "characters": [
            character_sheet(session, id_, until=until, count=count, text=False)
            for id_ in character_ids],
    }
