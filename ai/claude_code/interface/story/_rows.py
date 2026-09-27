#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.time_keeper import idea_alias
from data_access_logic.query import common_query
from db.schema import Character, Event, Location, Story
from db.schema_pydantic import to_dict_with
from db.stamp import Stamp


def event_row(event, *, text: bool = True) -> dict:
    data = to_dict_with(event, relations=common_query.EVENT_RELATIONS, text=text)
    data["characters"] = [
        {"id": link.character_id, "name": None if link.character is None else link.character.name}
        for link in event.event_characters]
    return data


def events_at(session: Session, when, *, place_ids=None, limit=None,
              text: bool = True) -> list[dict]:
    rows = session.scalars(
        common_query.events_at_select(when, place_ids=place_ids, limit=limit)).all()
    return [event_row(row, text=text) for row in rows]


def events_of(session: Session, select_fn, record_id: int, *, until=None, limit=5,
              text: bool = True) -> list[dict]:
    rows = session.scalars(select_fn(record_id, until=until, limit=limit)).all()
    return [event_row(row, text=text) for row in rows]


def open_events(session: Session, place_ids, until: Stamp) -> list[dict]:
    rows = session.scalars(common_query.open_events_select(place_ids, until)).all()
    return [event_row(row) for row in rows]


def residents(session: Session, place_ids, until: Stamp) -> list[int]:
    character_ids = session.scalars(
        common_query.resident_character_ids_select(place_ids, until)).all()
    return [id_ for id_ in character_ids if id_ is not None]


def _place_at(session: Session, select_fn, owner_id: int, until: Stamp) -> dict | None:
    row = session.scalars(select_fn(owner_id, until)).first()
    if row is None:
        return None
    return {"place_id": row.location_id,
            "place_name": None if row.place is None else row.place.name,
            "start": None if row.start is None else str(row.start)}


def character_sheet(session: Session, character_id: int, *, until=None,
                    count: int = 5, text: bool = True) -> dict:
    character = session.scalars(common_query.character_select(character_id)).first()
    if character is None:
        raise common_query.NotFoundError(f"character_id={character_id} という id の character が見つからない")
    at = common_query.span(until)[1] if until is not None else Stamp(99999, 12, 31, 23, 59, 59)

    sheet = to_dict_with(character, text=text)
    # 時刻を渡さないときは、期間を限らない値だけを重ねる
    sheet.update(character.parameters_at(None if until is None else at))
    sheet["place"] = _place_at(session, common_query.character_place_select, character_id, at)
    sheet["recent_events"] = events_of(
        session, common_query.events_of_character_select, character_id, until=None if until is None else at,
        limit=count, text=text)
    return sheet


def story_digest(session: Session, story: Story) -> dict:
    episodes = session.scalars(common_query.story_episodes_select(story.id)).all()
    digest = to_dict_with(
        story, relations={"world": "world_name", "place": "place_name"})
    digest["episode_count"] = len(episodes)
    digest["last_episode"] = _episode_head(episodes[-1]) if episodes else None
    digest["unsynced"] = [_episode_head(episode) for episode in episodes if not episode.synced]
    return digest


def _episode_head(episode) -> dict:
    return {"id": episode.id, "start": None if episode.start is None else str(episode.start),
            "title": episode.title}


def stories(session: Session) -> list[dict]:
    rows = session.scalars(common_query.stories_select()).all()
    return [story_digest(session, story) for story in rows]


def episode_row(episode, *, text: bool = True) -> dict:
    """話の枠の列に、本文(`text`)と字数(`letters`)を足す。"""
    data = to_dict_with(episode)
    data["letters"] = episode.episode_text.letters if episode.episode_text is not None else 0
    if text:
        data["text"] = episode.body
    return data


def episodes(session: Session, story_id: int, *, count: int = 10, before=None,
             text: bool = True) -> list[dict]:
    common_query._get(session, Story, story_id, "story_id")
    rows = session.scalars(
        common_query.episodes_select(story_id, count=count, before=before)).all()
    return [episode_row(episode, text=text) for episode in reversed(rows)]


def unsynced_episodes(session: Session, story_id: int | None = None) -> list[dict]:
    rows = session.scalars(common_query.unsynced_episodes_select(story_id)).all()
    return [{"id": episode.id, "story_id": episode.story_id,
             "story_name": None if episode.story is None else episode.story.name,
             "start": None if episode.start is None else str(episode.start),
             "title": episode.title}
            for episode in rows]


def brief(session: Session, place_id: int, when=None, *, reach: int = 60,
          full: bool = False) -> dict:
    location = common_query._get(session, Location, place_id, "place_id")
    if when is None:
        raise ValueError("時刻が決まらない(when を渡す)")
    since, until = common_query.span(when)
    place_ids = common_query.descendant_place_ids(session, place_id)

    def visible(rows):
        if full:
            return rows
        return [row for row in rows if not row.get("hidden")]

    recent_query = (select(Event)
                    .options(*common_query.EVENT_LOAD_OPTIONS)
                    .where(Event.location_id.in_(place_ids),
                           Event.time <= until,
                           Event.time >= Stamp(max(1, since.year - reach)))
                    .order_by(Event.time.desc(), Event.id.desc()))
    recent = [event_row(row) for row in session.scalars(recent_query).all()]

    character_ids = residents(session, place_ids, until)
    ideas = idea_alias.essences(session, session.scalars(
        common_query.ideas_select(common_query.idea_scope_ids(session, place_id), until)).all())
    called = idea_alias.called(session, [idea.id for idea in ideas], place_id, until)

    character_names = _names_for(session, character_ids, "Character")

    return {
        "place": to_dict_with(location),
        "path": common_query.place_path(session, place_id),
        "time": str(until),
        "reach": reach,
        "open_events": visible(open_events(session, place_ids, until)),
        "recent_events": visible(recent),
        "ideas": [{"id": idea.id, "name": idea_alias.name_of(idea, called), "kind": idea.kind,
                   "text": idea_alias.text_of(idea, called)} for idea in ideas],
        "present_characters": [
            {"id": id_, "name": character_names.get(id_)} for id_ in character_ids],
    }


_NAME_MODELS = {"Character": Character, "Location": Location}


def _names_for(session: Session, ids: list[int], model_name: str) -> dict[int, str | None]:
    if not ids:
        return {}
    model = _NAME_MODELS[model_name]
    rows = session.scalars(select(model).where(model.id.in_(ids))).all()
    return {row.id: row.name for row in rows}


def cast(session: Session, story_id: int, when=None, *, count: int = 5,
         levels: int = 1) -> dict:
    story = common_query._get(session, Story, story_id, "story_id")
    if story.place_id is None:
        raise ValueError(f"作品 {story.name} に立つ場所(place_id)が無い")
    _, until = common_query.resolve_time(session, when, story)
    root_id = common_query.place_up(session, story.place_id, levels)
    place_ids = common_query.descendant_place_ids(session, root_id)
    character_ids = residents(session, place_ids, until)
    return {
        "story": {"id": story.id, "name": story.name},
        "time": str(until),
        "scope": {"id": root_id, "name": _names_for(session, [root_id], "Location").get(root_id),
                  "path": common_query.place_path(session, root_id)},
        "characters": [
            character_sheet(session, id_, until=until, count=count, text=False)
            for id_ in character_ids],
    }
