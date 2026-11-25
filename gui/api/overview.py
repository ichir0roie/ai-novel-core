#!/usr/bin/env python3
"""動きの見取り図(`/overview`)の元データ。選んだ章の話の期間を軸に、その期間の話(どの作品のものも)と出来事を俯瞰する。

出来事は作品に結ばないので、章に関わらず期間の重なるものをすべて出す。
"""
from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from data_access_logic.query import common_query
from db.schema import (
    ChangeOp, Character, CharacterLocation, Episode, Event, Expansion, ExpansionChange, IdeaHistory, Location, Story,
)
from db.stamp import Stamp
from gui.api.models import OverviewCharacter, OverviewEpisode, OverviewEvent, OverviewResponse, OverviewSize

# 展開が足した行のうち、行の数をそのまま出来事の大きさに数える表。事柄は、候補のアイデアを足すと呼び名の行が二つ増えるので、
# 足した呼び名の行が指すアイデアの数で数える
_SIZE_TABLES = {
    CharacterLocation.__tablename__: "moves",
    Location.__tablename__: "locations",
    Character.__tablename__: "new_characters",
}
# 人物モードが展開に残す、居合わせて互いに応じた相手の見出し(`flows/act.py` の `MET_HEAD`)
_DIALOGUE_HEAD = "居合わせた相手とのやり取り:"


def _text(value: Stamp | None) -> str | None:
    return None if value is None else str(value)


def _window(spans: list[tuple[Stamp, Stamp | None]]) -> tuple[Stamp, Stamp]:
    if not spans:
        raise ValueError("この章には時刻のある話が無いので、期間を決められない")
    return min(start for start, _ in spans), max(end or start for start, end in spans)


def _invited_names(prompt: str) -> list[str]:
    if _DIALOGUE_HEAD not in prompt:
        return []
    lines = prompt.split(_DIALOGUE_HEAD, 1)[1].splitlines()
    return [line[2:].split(":", 1)[0] for line in lines if line.startswith("- ") and ":" in line]


def overview(s: Session, story_id: int, since: Stamp | None = None, until: Stamp | None = None) -> OverviewResponse:
    """`since`〜`until` に掛かる話と出来事。省いた端は章の話の始まり・終わり。画面はスクロールした先の期間を足して読む"""
    story = common_query.get_row(s, Story, story_id)
    chapter_ids = common_query.descendant_story_ids(s, story_id)
    episode_spans = s.execute(select(Episode.start, Episode.end)
                              .where(Episode.story_id.in_(chapter_ids), Episode.start.is_not(None))).all()
    chapter_since, chapter_until = _window([(start, end) for start, end in episode_spans if start is not None])
    since = since or chapter_since
    until = until or chapter_until

    found = s.scalars(select(Episode).where(
        Episode.start.is_not(None), Episode.start <= until,
        func.coalesce(Episode.end, Episode.start) >= since).order_by(Episode.start, Episode.id)).all()
    story_names = dict(s.execute(select(Story.id, Story.name)
                                 .where(Story.id.in_({episode.story_id for episode in found}))).all())
    episodes = [OverviewEpisode(id=episode.id, title=episode.title, start=str(episode.start), end=_text(episode.end),
                                story_id=episode.story_id, story_name=story_names.get(episode.story_id),
                                in_story=episode.story_id in chapter_ids)
                for episode in found if episode.start is not None]

    events = s.scalars(
        select(Event).options(selectinload(Event.event_characters), joinedload(Event.location))
        .where(Event.time <= until, func.coalesce(Event.end, Event.time) >= since)
        .order_by(Event.time, Event.id)
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

    participant_ids = {link.character_id for event in events for link in event.event_characters}
    names = dict(s.execute(select(Character.id, Character.name).where(Character.id.in_(participant_ids))).all())

    overview_events = []
    for event in events:
        ids = [link.character_id for link in event.event_characters]
        expansion = expansions.get(expansion_of.get(event.id, -1))
        counted = parts[expansion.id] if expansion is not None and act_event_of[expansion.id] == event.id else Counter()
        invited = [] if expansion is None else [
            id_ for id_ in ids if id_ != expansion.actor_id and names.get(id_) in _invited_names(expansion.prompt)]
        overview_events.append(OverviewEvent(
            id=event.id, name=event.name, start=str(event.time), end=_text(event.end), parent_event_id=event.parent_event_id,
            location_name=None if event.location is None else event.location.name, origin=event.origin,
            hidden=bool(event.hidden), importance=event.importance, text=event.text or "", character_ids=ids,
            expansion_id=None if expansion is None else expansion.id,
            actor_id=None if expansion is None else expansion.actor_id, invited_ids=invited,
            expansion_summary=None if expansion is None else expansion.summary,
            expansion_prompt=None if expansion is None else expansion.prompt,
            size=OverviewSize(people=len(ids), moves=counted["moves"], locations=counted["locations"],
                              new_characters=counted["new_characters"], ideas=counted["ideas"],
                              total=len(ids) + sum(counted.values()))))

    return OverviewResponse(
        story_id=story.id, story_name=story.name, chapter_since=str(chapter_since), chapter_until=str(chapter_until),
        since=str(since), until=str(until), episodes=episodes, events=overview_events,
        characters=[OverviewCharacter(id=id_, name=name) for id_, name in sorted(names.items())])
