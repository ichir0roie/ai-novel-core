#!/usr/bin/env python3
"""場所に居合わせる人物・対象から、当事者ごとの推測 → 候補をサイコロ → 記録、の順で出来事を一件起こす。"""
from __future__ import annotations

import random

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ai.instructions.event_writing import (
    CHARACTER_TEXT_UPDATE_INSTRUCTION, CHARACTER_NOTE_LIMIT, CHARACTER_NOTE_SEPARATOR,
    EVENT_AGE_INSTRUCTION, EVENT_PROGRESSION_INSTRUCTION, EVENT_RECORD_INSTRUCTION, RECENT_EVENT_LIMIT,
)
from ai.instructions.naming import PLACE_NAMING_INSTRUCTION, fill_name_placeholder
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.cast import participants_at
from data_access_logic.event.progress_models import (
    CandidateDraft, CandidateRequest, CandidateRequestSerialized, CandidatesDraft, EventRecordDraft,
    JudgementDraft, JudgementRequest, JudgementRequestSerialized, ParticipantJudgement,
    PlaceSituationMaterial, RecordRequest, RecordRequestSerialized,
)
from data_access_logic.event.summary import summarized_events
from data_access_logic.location.models import LocationMaterial, PlaceMaterial
from data_access_logic.query import common_query, story_createion_query, world_createion_query
from data_access_logic.query.base import location_active_condition
from db.schema import Character, CharacterPlace, ConfirmStatus, Event, EventCharacter, Location
from db.stamp import Stamp
from randomizer.random_location_generator import build_location

# 一度に居合わせる人物として渡す上限
_PARTICIPANT_LIMIT = 20

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_DAYS_IN_400_YEARS = 146097

_SITUATION_INSTRUCTION = """\
場所の状況は日本語の見出しを付けた JSON で渡す。
- 居合わせる人物・対象の種別が「人物」以外なら、国・組織・集団・物。年齢は人物なら歳、それ以外は成立からの年数。
  関係はその時点で続いている相関、直近の出来事はその者自身が場所を問わず関わった直近の出来事の名前。性格の各軸は 無/低/並/高/必 の五段階。
- 主役を渡したときは、主役の身に起きる次の出来事として考え、主役を当事者に必ず含める。主役の直前の出来事が終わった後に起きる出来事にする。
- 場面の指定を渡したときは、候補も記録も、すべてこの指定に沿った出来事にする。
- 「この時点より後に既に決まっている出来事」は、これと矛盾させず、先回りして起こさない。
- 進めたい筋書きは、上位の場所のものから順につなげた作品の本文。"""

_JUDGEMENT_SYSTEM_PROMPT = f"""\
あなたは架空の世界観の中で、ある一人の人物、または人物以外の一つの対象(国・組織・集団・物)の立場に立って考える設定作家です。
場所の状況と「この当事者」を渡すので、この当事者のいまを、その種別・人物像・口調・方言・性格・立場から推測してください。
人物なら性格と人間関係から、人物以外なら方針と力の及ぶ範囲から。
{_SITUATION_INSTRUCTION}
{EVENT_AGE_INSTRUCTION}
他の当事者のことは決めない。この当事者自身のことだけを書く。"""

_CANDIDATE_SYSTEM_PROMPT = f"""\
あなたは、ある場所に起こる出来事を列挙する作家です。
場所の状況と、当事者ごとの思考・感情・望み・恐れ・行動を渡すので、
これらの行動が同じ場で重なった結果として、この時点で起こりうる出来事の候補を{constants.CANDIDATE_COUNT}件挙げてください。
日常の小さな、感情がぶつかる、偶発的な(事故・天候・病・思いがけない出会い)、居場所が変わる(旅立ち・帰還・避難)、
笑いや祝い、取り決めや対立が動くなど、種類の違うものを混ぜてください。
各候補は当事者の行動と矛盾しない範囲で立てる。
出来事の種(時代・場所を抜いた、別の物語から取ったアイデア)を渡したときは、候補は、この種のどれかをこの場所・この時点・この当事者に合わせて具体化したものか、直前・直近の出来事から連想したものにする。
{_SITUATION_INSTRUCTION}
{EVENT_AGE_INSTRUCTION}
{EVENT_PROGRESSION_INSTRUCTION}"""

_RECORD_SYSTEM_PROMPT = f"""\
あなたは架空の世界観の中で、ある場所に起きたことを記録する設定作家です。
場所の状況、移動先の候補、当事者ごとの思考・感情・望み・恐れ・行動、サイコロで選ばれた出来事の候補を渡すので、その候補をこの場所にこの時点で起きた出来事として1件、記録に起こしてください。
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
選ばれた出来事の候補(名前と概要)を、当事者ごとの思考・感情・望み・恐れ・行動を土台にして記録に起こす。
候補の筋から外れない。event_text 内では id ではなく名前で書く。
{EVENT_RECORD_INSTRUCTION}

character_updates の text の書き方:
{CHARACTER_TEXT_UPDATE_INSTRUCTION}"""


def _days_in_month(year: int, month: int) -> int:
    if month == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        return 29
    return _MONTH_DAYS[month - 1]


def _days_before_year(year: int) -> int:
    y = year - 1
    return 365 * y + y // 4 - y // 100 + y // 400


def _add_days(time: Stamp, days: int) -> Stamp:
    """出来事の終わり(始まりから続いた日数ぶん後)。月末・閏年をまたいで数える。"""
    ordinal = _days_before_year(time.year) + sum(_days_in_month(time.year, m) for m in range(1, time.month)) + time.day
    ordinal += days
    year = ordinal * 400 // _DAYS_IN_400_YEARS + 1
    while _days_before_year(year) >= ordinal:
        year -= 1
    while _days_before_year(year + 1) < ordinal:
        year += 1
    day = ordinal - _days_before_year(year)
    month = 1
    while day > _days_in_month(year, month):
        day -= _days_in_month(year, month)
        month += 1
    return Stamp(year, month, day, time.hour, time.minute, time.second)


def _situation(
    s: Session, ai: AIClient, place_id: int, characters: list[Character], time: Stamp,
    focus: Character | None, scene: str | None, use_story: bool,
) -> PlaceSituationMaterial:
    place = PlaceMaterial.model_validate(s.get_one(Location, place_id))
    stories = story_createion_query.load_location_story(s, place_id, time) if use_story else []
    story_recent_events = []
    if stories:
        # 横(兄弟の場所)の出来事は含めない。作品の配下全体を渡すと、他の国の展開まで持ち込まれて
        # 場所ごとの差が消えるため(2026-09 に観測)
        place_ids = []
        for step in reversed(common_query.place_path(s, place_id)):
            place_ids.append(step.id)
            if step.id == stories[0].place_id:
                break
        story_recent_events = s.scalars(
            common_query.events_in_locations_select(place_ids, until=time, limit=RECENT_EVENT_LIMIT)).all()
    focus_previous = (
        summarized_events(s, ai, common_query.latest_character_event_select(focus.id, until=time))
        if focus is not None else [])

    return PlaceSituationMaterial(
        time=time,
        place=place,
        participants=participants_at(s, characters[:_PARTICIPANT_LIMIT], time),
        recent_events=s.scalars(
            common_query.events_of_place_select(place_id, until=time, limit=RECENT_EVENT_LIMIT)).all(),
        later_events=summarized_events(
            s, ai,
            common_query.events_after_select(
                place_id, [character.id for character in characters], time, limit=constants.LATER_EVENT_LIMIT)),
        stories=stories,
        story_recent_events=story_recent_events,
        focus_character=focus,
        focus_previous_event=focus_previous[0] if focus_previous else None,
        scene=scene,
    )


def _judgements(ai: AIClient, situation: PlaceSituationMaterial) -> list[ParticipantJudgement]:
    judgements = []
    for participant in situation.participants:
        prompt = "\n".join([
            JudgementRequestSerialized.model_validate(
                JudgementRequest(situation=situation, participant=participant)).model_dump_json(indent=2),
            "この当事者のいまの思考・感情・望み・恐れ・行動を推測してください。",
        ])
        decided = ai.try_generate_json(prompt, JudgementDraft.model_json_schema(), system=_JUDGEMENT_SYSTEM_PROMPT)
        try:
            judgement = JudgementDraft.model_validate(decided)
        except ValidationError:
            continue
        judgements.append(ParticipantJudgement(character=participant.character, judgement=judgement))
    return judgements


def _rolled_candidate(
    ai: AIClient, rng: random.Random, situation: PlaceSituationMaterial,
    judgements: list[ParticipantJudgement], seeds: list[str],
) -> CandidateDraft | None:
    prompt = "\n".join([
        CandidateRequestSerialized.model_validate(
            CandidateRequest(situation=situation, judgements=judgements, seeds=seeds)).model_dump_json(indent=2),
        f"この場所にこの時点で起こりうる出来事の候補を{constants.CANDIDATE_COUNT}件挙げてください。",
    ])
    decided = ai.try_generate_json(prompt, CandidatesDraft.model_json_schema(), system=_CANDIDATE_SYSTEM_PROMPT)
    try:
        candidates = CandidatesDraft.model_validate(decided).candidates
    except ValidationError:
        return None
    if not candidates:
        return None
    chosen = rng.choice(candidates)
    print(f"[data_access_logic/event] 候補 {candidates.index(chosen) + 1}/{len(candidates)}: {chosen.name}")
    return chosen


def _destinations(s: Session, place_id: int, time: Stamp) -> list[LocationMaterial]:
    root_id = common_query.place_up(s, place_id, constants.REACH_LEVELS)
    nearby_ids = set(common_query.descendant_place_ids(s, root_id)) - {place_id, root_id}
    places = s.scalars(
        world_createion_query.alive_locations_select(time)
        .where(Location.id.in_(nearby_ids), location_active_condition(time))
    ).all()
    return [LocationMaterial.model_validate(place) for place in places[:constants.MOVE_DESTINATION_LIMIT]]


def _append_note(record: Character, note: str) -> None:
    if not record.text:
        record.text = note
        return
    base, *notes = record.text.split(CHARACTER_NOTE_SEPARATOR)
    notes.append(note)
    notes = notes[-(CHARACTER_NOTE_LIMIT - 1):] if CHARACTER_NOTE_LIMIT > 1 else []
    record.text = CHARACTER_NOTE_SEPARATOR.join([base, *notes])


def progress_place(
    s: Session,
    ai: AIClient,
    rng: random.Random,
    place_id: int,
    characters: list[Character],
    time: Stamp,
    seeds: list[str],
    focus: Character | None = None,
    scene: str | None = None,
    use_story: bool = False,
) -> Event | None:
    """起こした出来事は `confirmed=未確認` で足す。本文は記録のままで、小説にするのは `novelist.novelize_event`。"""
    situation = _situation(s, ai, place_id, characters, time, focus, scene, use_story)
    judgements = _judgements(ai, situation)
    candidate = _rolled_candidate(ai, rng, situation, judgements, seeds)
    if candidate is None:
        return None
    destinations = _destinations(s, place_id, time)

    hints = []
    if situation.stories:
        hints.append("進めたい筋書きがあるなら、そこへ向かう一歩になる出来事を優先する。")
    if use_story:
        hints.append("居合わせる人物・対象の人物像に筋書きが書かれていれば、その者個人について進めたい筋書きとして扱い、"
                     "そこへ向かう一歩になる出来事を優先する。")
    prompt = "\n".join([
        RecordRequestSerialized.model_validate(RecordRequest(
            situation=situation, judgements=judgements, destinations=destinations, candidate=candidate,
        )).model_dump_json(indent=2),
        "この候補を、この場所にこの時点で起きた出来事として記録してください。",
        *hints,
    ])
    decided = ai.try_generate_json(prompt, EventRecordDraft.model_json_schema(), system=_RECORD_SYSTEM_PROMPT)
    try:
        draft = EventRecordDraft.model_validate(decided)
    except ValidationError as error:
        print(f"[data_access_logic/event] 場所id={place_id}: 記録が得られなかった: {error}")
        return None

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
        for current in s.scalars(common_query.character_place_select(character.id, time)).all():
            current.end = time
        s.add(CharacterPlace(character_id=character.id, location_id=destination.id, start=time, end=character.end))
        if character.id not in involved_ids:
            involved_ids.append(character.id)
        move_notes.append(f"{character.name} → {destination.name}")

    end = _add_days(time, draft.event_duration_days)
    record = Event(
        name=draft.event_name,
        text=draft.event_text,
        time=time,
        location_id=place_id,
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
        _append_note(character, note)
        update_notes.append(f"{character.name}: text+={note}")

    place = s.get_one(Location, place_id)
    location_notes = []
    if draft.location_abolished and place.end is None:
        place.end = time
        location_notes.append(f"{place.name}(id={place_id}): 消滅")
    founded = draft.location_founded
    if founded is not None and founded.name.strip():
        new_location = Location(**build_location(
            parent_id=place_id,
            name=founded.name,
            kind=founded.kind or "集落",
            text=founded.text,
            environment=founded.environment or place.environment,
            start=time,
            active_random_generation=place.active_random_generation,
        ))
        s.add(new_location)
        s.flush()
        location_notes.append(f"{new_location.name}(id={new_location.id}): 新設")

    s.commit()
    involved_names = [name for name in (by_id[character_id].name for character_id in involved_ids) if name]
    print(f"[data_access_logic/event] {time} 場所id={place_id}: {record.name}"
          f" / 継続: {draft.event_duration_days}日({time}〜{end})"
          + (f" / 関わった: {', '.join(involved_names)}" if involved_names else "")
          + (f" / 移動: {'; '.join(move_notes)}" if move_notes else "")
          + (f" / 人物・対象更新: {'; '.join(update_notes)}" if update_notes else "")
          + (f" / 場所: {'; '.join(location_notes)}" if location_notes else ""))
    return record
