#!/usr/bin/env python3
"""場所に居合わせる人物・対象から、候補をサイコロ → 記録、の順で出来事を一件起こす。

db だけの段(`situation_targets` → 要約を揃える → `situation` / `destinations` → `save_progress`)と、
AI・乱数だけの段(`rolled_candidate` → `record_draft`)に分けてある。手元では `progress_location` がつなぎ、
web のセッションでは `web_session/event.py` が API 越しにつなぐ。
"""
from __future__ import annotations

import logging
import random

from sqlalchemy import Select
from sqlalchemy.orm import Session

from ai.instructions.event_writing import (
    CHARACTER_TEXT_UPDATE_INSTRUCTION, EVENT_AGE_INSTRUCTION,
    EVENT_PROGRESSION_INSTRUCTION, EVENT_RECORD_INSTRUCTION, RECENT_EVENT_LIMIT,
)
from ai.instructions.naming import PLACE_NAMING_INSTRUCTION, fill_name_placeholder
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import participants_at
from data_access_logic.character.histories import add_history
from data_access_logic.event.progress_models import (
    CandidateDraft, CandidateRequestSerialized, CandidatesDraft, EventRecordDraft, LocationSituationMaterial,
    LocationSituationSerialized, RecordRequestSerialized,
)
from data_access_logic.event.summary import events_of
from data_access_logic.location.models import LocationMaterial, LocationTextMaterial
from data_access_logic.query import common_query, story_creation_query, world_creation_query
from data_access_logic.summary_targets import SummaryTargets, refresh
from db.schema import Character, CharacterLocation, ConfirmStatus, Event, EventCharacter, Location
from db.stamp import Stamp

logger = logging.getLogger(__name__)

# 一度に居合わせる人物として渡す上限
_PARTICIPANT_LIMIT = 20

_SITUATION_INSTRUCTION = """\
場所の状況は日本語の見出しを付けた JSON で渡す。
- 居合わせる人物・対象の種別が「人物」以外なら、国・組織・集団・物。年齢は人物なら歳、それ以外は成立からの年数。
  関係はその時点で続いている相関、直近の出来事はその者自身が場所を問わず関わった直近の出来事の名前。性格の各軸は 無/低/並/高/必 の五段階。
- 主役を渡したときは、主役の身に起きる次の出来事として考え、主役を当事者に必ず含める。主役の直前の出来事が終わった後に起きる出来事にする。
- 場面の指定を渡したときは、候補も記録も、すべてこの指定に沿った出来事にする。
- 「この時点より後に既に決まっている出来事」は、これと矛盾させず、先回りして起こさない。
- 進めたい筋書きは、上位の場所のものから順につなげた作品の本文。"""

_CANDIDATE_SYSTEM_PROMPT = f"""\
あなたは、ある場所に起こる出来事を列挙する作家です。
場所の状況を渡すので、居合わせる人物・対象それぞれの人物像・性格・関係・立場から、
それぞれがいま取りそうな行動が同じ場で重なった結果として、この時点で起こりうる出来事の候補を{constants.CANDIDATE_COUNT}件挙げてください。
日常の小さな、感情がぶつかる、偶発的な(事故・天候・病・思いがけない出会い)、居場所が変わる(旅立ち・帰還・避難)、
笑いや祝い、取り決めや対立が動くなど、種類の違うものを混ぜてください。
各候補は当事者の人物像・性格と矛盾しない範囲で立てる。
出来事の種(時代・場所を抜いた、別の物語から取ったアイデア)を渡したときは、候補は、この種のどれかをこの場所・この時点・この当事者に合わせて具体化したものか、直前・直近の出来事から連想したものにする。
{_SITUATION_INSTRUCTION}
{EVENT_AGE_INSTRUCTION}
{EVENT_PROGRESSION_INSTRUCTION}"""

_RECORD_SYSTEM_PROMPT = f"""\
あなたは架空の世界観の中で、ある場所に起きたことを記録する設定作家です。
場所の状況、移動先の候補、サイコロで選ばれた出来事の候補を渡すので、その候補をこの場所にこの時点で起きた出来事として1件、記録に起こしてください。
候補の名前は event_name にそのまま使うか、整えてもよい。
{_SITUATION_INSTRUCTION}
{EVENT_AGE_INSTRUCTION}
character_ids には、関わった人物・対象の人物idを、居合わせる人物・対象の中からだけ選んで入れる(複数可)。
character_moves は、この出来事で居場所が変わった人物だけ(旅立ち・移住・避難・帰還など)。場所idは移動先の候補からだけ選ぶ。誰も動いていなければ空にする。
この出来事が場所自身の改廃(消滅・新設)に及ぶときだけ、location_abolished / location_founded を埋める。
何も変わっていなければ location_abolished は false、location_founded は null のままにする。
location_founded の固有名詞は次の基準で名づける。
{PLACE_NAMING_INSTRUCTION}

event_text の書き方:
選ばれた出来事の候補(名前と概要)を、当事者それぞれの人物像・性格・関係を土台にして記録に起こす。
候補の筋から外れない。event_text 内では id ではなく名前で書く。
{EVENT_RECORD_INSTRUCTION}

character_updates の text の書き方:
{CHARACTER_TEXT_UPDATE_INSTRUCTION}"""


def _later_events_select(location_id: int, characters: list[Character], time: Stamp) -> Select[Event]:
    return common_query.events_after_select(
        location_id, [character.id for character in characters], time, limit=constants.LATER_EVENT_LIMIT)


def situation_targets(
    s: Session, location_id: int, characters: list[Character], time: Stamp, focus: Character | None,
) -> SummaryTargets:
    focus_previous = (s.scalars(common_query.latest_character_event_select(focus.id, until=time)).all()
                      if focus is not None else [])
    later_events = s.scalars(_later_events_select(location_id, characters, time)).all()
    return SummaryTargets(event_ids=[event.id for event in [*focus_previous, *later_events]])


def situation(
    s: Session, location_id: int, characters: list[Character], time: Stamp,
    focus: Character | None, scene: str | None, use_story: bool,
) -> LocationSituationSerialized:
    """要約は揃えてある前提でそのまま読む。"""
    location = LocationTextMaterial.model_validate(s.get_one(Location, location_id))
    stories = story_creation_query.load_location_story(s, location_id, time) if use_story else []
    story_recent_events = []
    if stories:
        # 横(兄弟の場所)の出来事は含めない。作品の配下全体を渡すと、他の国の展開まで持ち込まれて
        # 場所ごとの差が消えるため(2026-09 に観測)
        location_ids = []
        for step in reversed(common_query.location_path(s, location_id)):
            location_ids.append(step.id)
            if step.id == stories[0].location_id:
                break
        story_recent_events = s.scalars(
            common_query.events_in_locations_select(location_ids, until=time, limit=RECENT_EVENT_LIMIT)).all()
    focus_previous = (events_of(s, common_query.latest_character_event_select(focus.id, until=time))
                      if focus is not None else [])

    return LocationSituationSerialized(
        time=time,
        location=location,
        participants=participants_at(s, characters[:_PARTICIPANT_LIMIT], time),
        recent_events=s.scalars(
            common_query.events_of_location_select(location_id, until=time, limit=RECENT_EVENT_LIMIT)).all(),
        later_events=events_of(s, _later_events_select(location_id, characters, time)),
        stories=stories,
        story_recent_events=story_recent_events,
        focus_character=focus,
        focus_previous_event=focus_previous[0] if focus_previous else None,
        scene=scene,
    )


def rolled_candidate(
    ai: AIClient, rng: random.Random, situation: LocationSituationMaterial, seeds: list[str],
) -> CandidateDraft | None:
    prompt = "\n".join([
        CandidateRequestSerialized(situation=situation, seeds=seeds).model_dump_json(indent=2),
        f"この場所にこの時点で起こりうる出来事の候補を{constants.CANDIDATE_COUNT}件挙げてください。",
    ])
    decided = ai.generate(prompt, CandidatesDraft, system=_CANDIDATE_SYSTEM_PROMPT)
    if decided is None or not decided.candidates:
        return None
    candidates = decided.candidates
    chosen = rng.choice(candidates)
    logger.info(f"候補 {candidates.index(chosen) + 1}/{len(candidates)}: {chosen.name}")
    return chosen


def destinations(s: Session, location_id: int, time: Stamp) -> list[LocationMaterial]:
    root_id = common_query.location_up(s, location_id, constants.REACH_LEVELS)
    nearby_ids = set(common_query.descendant_location_ids(s, root_id)) - {location_id, root_id}
    locations = s.scalars(world_creation_query.active_locations_select(time, nearby_ids)).all()
    return [LocationMaterial.model_validate(location) for location in locations[:constants.MOVE_DESTINATION_LIMIT]]


def record_draft(
    ai: AIClient, situation: LocationSituationMaterial, destinations: list[LocationMaterial], candidate: CandidateDraft,
    use_story: bool,
) -> EventRecordDraft | None:
    hints = []
    if situation.stories:
        hints.append("進めたい筋書きがあるなら、そこへ向かう一歩になる出来事を優先する。")
    if use_story:
        hints.append("居合わせる人物・対象の人物像に筋書きが書かれていれば、その者個人について進めたい筋書きとして扱い、"
                     "そこへ向かう一歩になる出来事を優先する。")
    prompt = "\n".join([
        RecordRequestSerialized(situation=situation, destinations=destinations, candidate=candidate)
        .model_dump_json(indent=2),
        "この候補を、この場所にこの時点で起きた出来事として記録してください。",
        *hints,
    ])
    draft = ai.generate(prompt, EventRecordDraft, system=_RECORD_SYSTEM_PROMPT)
    if draft is None:
        logger.warning(f"{situation.location.name}: 記録が得られなかった")
    return draft


def save_progress(
    s: Session,
    location_id: int,
    characters: list[Character],
    time: Stamp,
    focus: Character | None,
    destinations: list[LocationMaterial],
    draft: EventRecordDraft,
) -> Event:
    """起こした出来事は `confirmed=未確認` で足す。"""
    by_id = {character.id: character for character in characters}
    involved_ids = list(dict.fromkeys(character_id for character_id in draft.character_ids if character_id in by_id))
    if focus is not None and focus.id not in involved_ids:
        involved_ids.insert(0, focus.id)

    destination_by_id = {destination.id: destination for destination in destinations}
    move_notes = []
    for move in draft.character_moves:
        character = by_id.get(move.character_id)
        destination = destination_by_id.get(move.location_id)
        if character is None or destination is None:
            continue
        for current in s.scalars(common_query.character_location_select(character.id, time)).all():
            current.end = time
        s.add(CharacterLocation(character_id=character.id, location_id=destination.id, start=time, end=character.end))
        if character.id not in involved_ids:
            involved_ids.append(character.id)
        move_notes.append(f"{character.name} → {destination.name}")

    end = time.plus_days(draft.event_duration_days)
    record = Event(
        name=draft.event_name,
        text=draft.event_text,
        time=time,
        location_id=location_id,
        start=time,
        end=end,
        confirmed=ConfirmStatus.PENDING,
        event_characters=[EventCharacter(character_id=character_id) for character_id in involved_ids],
    )
    s.add(record)

    update_notes = []
    for update in draft.character_updates:
        character = by_id.get(update.character_id)
        if character is None or not update.text:
            continue
        note = fill_name_placeholder(update.text, character.name or "")
        # 出来事の年から始まる行にするので、それより前の出来事・話には効かない
        add_history(character, time.year, note)
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
          + (f" / 移動: {'; '.join(move_notes)}" if move_notes else "")
          + (f" / 人物・対象更新: {'; '.join(update_notes)}" if update_notes else "")
          + (f" / 場所: {'; '.join(location_notes)}" if location_notes else ""))
    return record


def progress_location(
    s: Session,
    ai: AIClient,
    rng: random.Random,
    location_id: int,
    characters: list[Character],
    time: Stamp,
    seeds: list[str],
    focus: Character | None = None,
    scene: str | None = None,
    use_story: bool = False,
) -> Event | None:
    refresh(s, ai, situation_targets(s, location_id, characters, time, focus))
    current = situation(s, location_id, characters, time, focus, scene, use_story)
    candidate = rolled_candidate(ai, rng, current, seeds)
    if candidate is None:
        return None
    moves = destinations(s, location_id, time)
    draft = record_draft(ai, current, moves, candidate, use_story)
    if draft is None:
        return None
    record = save_progress(s, location_id, characters, time, focus, moves, draft)
    s.commit()
    return record
