#!/usr/bin/env python3
"""動きの見取り図(`/overview`)の元データ。選んだ章の期間の前後の出来事を、人物ごとの関わりと大きさで俯瞰する。"""
from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from data_access_logic.expansion import budget
from data_access_logic.query import common_query
from db.schema import (
    ChangeOp, Character, CharacterLocation, CharacterRelation, Episode, EpisodeCharacter, Event, Expansion,
    ExpansionChange, IdeaHistory, Location, Story,
)
from db.stamp import Stamp
from gui.api.models import (
    OverviewCharacter, OverviewEpisode, OverviewEvent, OverviewRelation, OverviewResponse, OverviewSize,
)

# 展開が足した行のうち、行の数をそのまま出来事の大きさに数える表。事柄は、候補のアイデアを足すと呼び名の行が二つ増えるので、
# 足した呼び名の行が指すアイデアの数で数える
_SIZE_TABLES = {
    CharacterLocation.__tablename__: "moves",
    Location.__tablename__: "locations",
    Character.__tablename__: "new_characters",
}
# 人物モードが展開に残す、巻きこんだ相手との手番の見出し(`flows/act.py` の `_prompt_text`)
_DIALOGUE_HEAD = "巻きこんだ相手とのやり取り:"


def _text(value: Stamp | None) -> str | None:
    return None if value is None else str(value)


def _window(episodes: list[Episode], margin_days: int) -> tuple[Stamp, Stamp]:
    starts = [episode.start for episode in episodes if episode.start is not None]
    if not starts:
        raise ValueError("この章には時刻のある話が無いので、期間を決められない")
    ends = [episode.end or episode.start for episode in episodes if episode.start is not None]
    return min(starts).plus_days(-margin_days), max(end for end in ends if end is not None).plus_days(margin_days)


def _invited_names(prompt: str) -> list[str]:
    if _DIALOGUE_HEAD not in prompt:
        return []
    lines = prompt.split(_DIALOGUE_HEAD, 1)[1].splitlines()
    return [line[2:].split(":", 1)[0] for line in lines if line.startswith("- ") and ":" in line]


def overview(s: Session, story_id: int, margin_days: int) -> OverviewResponse:
    story = common_query.get_row(s, Story, story_id)
    chapter_ids = common_query.descendant_story_ids(s, story_id)
    chapter_episodes = s.scalars(select(Episode).where(Episode.story_id.in_(chapter_ids), Episode.start.is_not(None))
                                 .order_by(Episode.start, Episode.id)).all()
    since, until = _window(list(chapter_episodes), margin_days)

    sibling_ids = ([] if story.parent_story_id is None else
                   [id_ for id_ in common_query.descendant_story_ids(s, story.parent_story_id)
                    if id_ not in chapter_ids and id_ != story.parent_story_id])
    siblings = s.scalars(select(Episode).where(
        Episode.story_id.in_(sibling_ids), Episode.start.is_not(None), Episode.start <= until,
        func.coalesce(Episode.end, Episode.start) >= since).order_by(Episode.start, Episode.id)).all()
    story_names = dict(s.execute(select(Story.id, Story.name).where(Story.id.in_([*chapter_ids, *sibling_ids]))).all())
    episodes = [OverviewEpisode(id=episode.id, title=episode.title, start=str(episode.start), end=_text(episode.end),
                                story_id=episode.story_id, story_name=story_names.get(episode.story_id),
                                in_story=episode.story_id in chapter_ids)
                for episode in [*chapter_episodes, *siblings] if episode.start is not None]

    events = s.scalars(
        select(Event).options(selectinload(Event.event_characters), joinedload(Event.location))
        .where(func.coalesce(Event.start, Event.time) <= until,
               func.coalesce(Event.end, Event.start, Event.time) >= since)
        .order_by(func.coalesce(Event.start, Event.time), Event.id)
        .execution_options(populate_existing=True)).all()
    event_ids = [event.id for event in events]

    # 人物モードの展開が足した出来事。一つの展開が企て(親)と一手の出来事を足したら、大きさは後に足した一手の出来事に付ける
    expansion_of = dict(s.execute(
        select(ExpansionChange.row_id, ExpansionChange.expansion_id)
        .join(Expansion, Expansion.id == ExpansionChange.expansion_id)
        .where(ExpansionChange.table_name == Event.__tablename__, ExpansionChange.op == ChangeOp.ADD,
               ExpansionChange.row_id.in_(event_ids))).all())
    expansions = {expansion.id: expansion for expansion in s.scalars(
        select(Expansion).where(Expansion.id.in_(set(expansion_of.values())))).all()}
    act_event_of = {expansion_id: max(id_ for id_, owner in expansion_of.items() if owner == expansion_id)
                     for expansion_id in expansions}
    parts: dict[int, Counter[str]] = defaultdict(Counter)
    for expansion_id, table, count in s.execute(
            select(ExpansionChange.expansion_id, ExpansionChange.table_name, func.count())
            .where(ExpansionChange.expansion_id.in_(expansions), ExpansionChange.op == ChangeOp.ADD,
                   ExpansionChange.table_name.in_(_SIZE_TABLES))
            .group_by(ExpansionChange.expansion_id, ExpansionChange.table_name)).all():
        parts[expansion_id][_SIZE_TABLES[table]] += count
    for expansion_id, count in s.execute(
            select(ExpansionChange.expansion_id, func.count(func.distinct(IdeaHistory.idea_id)))
            .join(IdeaHistory, IdeaHistory.id == ExpansionChange.row_id)
            .where(ExpansionChange.expansion_id.in_(expansions), ExpansionChange.op == ChangeOp.ADD,
                   ExpansionChange.table_name == IdeaHistory.__tablename__)
            .group_by(ExpansionChange.expansion_id)).all():
        parts[expansion_id]["ideas"] += count

    episode_counts = Counter(s.scalars(select(EpisodeCharacter.character_id).where(
        EpisodeCharacter.episode_id.in_([episode.id for episode in chapter_episodes]),
        EpisodeCharacter.mentioned.is_(False))).all())
    cast_ids = set(episode_counts)
    participant_ids = {link.character_id for event in events for link in event.event_characters}
    characters = s.scalars(select(Character).where(Character.id.in_(cast_ids | participant_ids))).all()
    names = {character.id: character.name for character in characters}

    overview_events = []
    for event in events:
        ids = [link.character_id for link in event.event_characters]
        expansion = expansions.get(expansion_of.get(event.id, -1))
        counted = parts[expansion.id] if expansion is not None and act_event_of[expansion.id] == event.id else Counter()
        invited = [] if expansion is None else [
            id_ for id_ in ids if id_ != expansion.actor_id and names.get(id_) in _invited_names(expansion.prompt)]
        start = event.start or event.time
        overview_events.append(OverviewEvent(
            id=event.id, name=event.name, start=str(start), end=_text(event.end), parent_event_id=event.parent_event_id,
            location_name=None if event.location is None else event.location.name, origin=event.origin,
            hidden=bool(event.hidden), text=event.text or "", character_ids=ids,
            expansion_id=None if expansion is None else expansion.id,
            actor_id=None if expansion is None else expansion.actor_id, invited_ids=invited,
            expansion_summary=None if expansion is None else expansion.summary,
            expansion_prompt=None if expansion is None else expansion.prompt,
            size=OverviewSize(people=len(ids), moves=counted["moves"], locations=counted["locations"],
                              new_characters=counted["new_characters"], ideas=counted["ideas"],
                              total=len(ids) + sum(counted.values()))))

    appearances = Counter(id_ for event in overview_events for id_ in event.character_ids)
    influences = {character.id: budget.influence_of(character, until) for character in characters}
    ordered = sorted(characters, key=lambda character: (
        -budget.rank(influences[character.id]), -episode_counts[character.id], -appearances[character.id],
        character.id))
    relations = s.scalars(select(CharacterRelation).where(
        CharacterRelation.character_1_id.in_(names), CharacterRelation.character_2_id.in_(names),
        or_(CharacterRelation.start.is_(None), CharacterRelation.start <= until),
        or_(CharacterRelation.end.is_(None), CharacterRelation.end >= since)).order_by(CharacterRelation.id)).all()
    return OverviewResponse(
        story_id=story.id, story_name=story.name, since=str(since), until=str(until), episodes=episodes,
        events=overview_events,
        characters=[OverviewCharacter(id=character.id, name=character.name, main_character=character.main_character,
                                      in_cast=character.id in cast_ids,
                                      influence=influences[character.id])
                    for character in ordered],
        relations=[OverviewRelation(id=relation.id, character_1_id=relation.character_1_id,
                                    character_2_id=relation.character_2_id, relation=relation.relation,
                                    start=_text(relation.start), end=_text(relation.end)) for relation in relations])
