#!/usr/bin/env python3
"""場所に居合わせる人物・対象から、候補をサイコロ → 記録、の順で出来事を一件起こす。

db だけの段(`situation_targets` → 要約を揃える → `situation` / `destinations` → `save_progress`)と、
AI・乱数だけの段(`rolled_candidate` → `record_draft`)に分けてある。流れ(`data_access_logic/flows/event.py`)がつなぐ。
"""
from __future__ import annotations

import logging
import random

from sqlalchemy import Select
from sqlalchemy.orm import Session

from ai.instructions.naming import fill_name_placeholder
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import participants_at
from data_access_logic.character.moves import allowed_moves
from data_access_logic.character.histories import add_history
from data_access_logic.event.progress_models import (
    CandidateDraft, CandidateRequestSerialized, CandidatesDraft, EventRecordDraft, LocationSituationMaterial,
    LocationSituationSerialized, RecordRequestSerialized,
)
from data_access_logic.event.summary import events_of
from data_access_logic.location.models import LocationMaterial
from data_access_logic.location.reading import location_at
from data_access_logic.query import common_query
from data_access_logic.summary_targets import SummaryTargets
from db.schema import Character, Event, EventCharacter, Location, StyleScope
from db.stamp import Stamp

logger = logging.getLogger(__name__)

# 一度に居合わせる人物として渡す上限
_PARTICIPANT_LIMIT = 20


def _later_events_select(location_id: int, characters: list[Character], time: Stamp) -> Select[Event]:
    return common_query.events_after_select(
        location_id, [character.id for character in characters], time, limit=constants.LATER_EVENT_LIMIT)


def situation_targets(s: Session, location_id: int, characters: list[Character], time: Stamp) -> SummaryTargets:
    return SummaryTargets(
        event_ids=[event.id for event in s.scalars(_later_events_select(location_id, characters, time)).all()])


def situation(
    s: Session, location_id: int, characters: list[Character], time: Stamp, scene: str | None,
) -> LocationSituationSerialized:
    """要約は揃えてある前提でそのまま読む。"""
    return LocationSituationSerialized(
        time=time,
        location=location_at(s.get_one(Location, location_id), time),
        participants=participants_at(s, characters[:_PARTICIPANT_LIMIT], time),
        recent_events=s.scalars(
            common_query.events_of_location_select(location_id, until=time, limit=constants.RECENT_EVENT_LIMIT)).all(),
        later_events=events_of(s, _later_events_select(location_id, characters, time)),
        scene=scene,
    )


def rolled_candidate(
    ai: AIClient, rng: random.Random, situation: LocationSituationMaterial, seeds: list[str],
) -> CandidateDraft | None:
    prompt = "\n".join([
        CandidateRequestSerialized(situation=situation, seeds=seeds).model_dump_json(indent=2),
        f"この場所にこの時点で起こりうる出来事の候補を{constants.CANDIDATE_COUNT}件挙げる。",
    ])
    decided = ai.generate(prompt, CandidatesDraft, instruction=StyleScope.EVENT_CANDIDATES)
    if decided is None or not decided.candidates:
        return None
    candidates = decided.candidates
    chosen = rng.choice(candidates)
    logger.info(f"候補 {candidates.index(chosen) + 1}/{len(candidates)}: {chosen.name}")
    return chosen


def record_draft(
    ai: AIClient, situation: LocationSituationMaterial, destinations: list[LocationMaterial], candidate: CandidateDraft,
) -> EventRecordDraft | None:
    prompt = "\n".join([
        RecordRequestSerialized(situation=situation, destinations=destinations, candidate=candidate)
        .model_dump_json(indent=2),
        "この候補を、この場所にこの時点で起きた出来事として記録する。",
    ])
    draft = ai.generate(prompt, EventRecordDraft, instruction=StyleScope.EVENT_RECORD)
    if draft is None:
        logger.warning(f"{situation.location.name}: 記録が得られなかった")
    return draft


def save_progress(
    s: Session,
    location_id: int,
    characters: list[Character],
    time: Stamp,
    destinations: list[LocationMaterial],
    draft: EventRecordDraft,
) -> Event:
    by_id = {character.id: character for character in characters}
    involved_ids = list(dict.fromkeys(character_id for character_id in draft.character_ids if character_id in by_id))
    # 居場所を移す人物も当事者に入れる(移すのは流れが `character.steps.move_characters` で行う)
    moves = allowed_moves(draft.character_moves, by_id, [destination.id for destination in destinations])
    involved_ids.extend(move.character_id for move in moves if move.character_id not in involved_ids)

    end = time.plus_days(draft.event_duration_days)
    record = Event(
        name=draft.event_name,
        text=draft.event_text,
        time=time,
        location_id=location_id,
        start=time,
        end=end,
        event_characters=[EventCharacter(character_id=character_id) for character_id in involved_ids],
    )
    s.add(record)

    update_notes = []
    for update in draft.character_updates:
        character = by_id.get(update.character_id)
        if character is None or not update.text:
            continue
        note = fill_name_placeholder(update.text, character.name or "")
        # 出来事の時刻から始まる行にするので、それより前の出来事・話には効かない
        add_history(character, time, note)
        update_notes.append(f"{character.name}: histories+={note}")

    location = s.get_one(Location, location_id)
    location_notes = []
    if draft.location_abolished and location.end is None:
        location.end = time
        location_notes.append(f"{location.name}(id={location_id}): 消滅")
    founded = draft.location_founded
    if founded is not None and founded.name.strip():
        new_location = Location(
            parent_id=location_id,
            name=founded.name,
            kind=founded.kind or "集落",
            text=founded.text,
            environment=founded.environment or location.environment,
            start=time,
            active_random_generation=location.active_random_generation,
        )
        s.add(new_location)
        s.flush()
        location_notes.append(f"{new_location.name}(id={new_location.id}): 新設")

    s.flush()
    involved_names = [name for name in (by_id[character_id].name for character_id in involved_ids) if name]
    logger.info(f"{time} 場所id={location_id}: {record.name}"
          f" / 継続: {draft.event_duration_days}日({time}〜{end})"
          + (f" / 関わった: {', '.join(involved_names)}" if involved_names else "")
          + (f" / 人物・対象更新: {'; '.join(update_notes)}" if update_notes else "")
          + (f" / 場所: {'; '.join(location_notes)}" if location_notes else ""))
    return record
