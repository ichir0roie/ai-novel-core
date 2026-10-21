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

from ai.instructions.materials import EVENT_PARTICIPANT_NOTE
from ai.instructions.naming import NAME_PLACEHOLDER, fill_name_placeholder
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

_SITUATION_NOTE = f"""\
{EVENT_PARTICIPANT_NOTE}
場面の指定を渡したときは、候補も記録も、すべてこの指定に沿った出来事にする。"""

_CANDIDATES_SYSTEM = f"""\
場所の状況を渡すので、居合わせる人物・対象それぞれの人物像・性格・関係・立場から、
それぞれがいま取りそうな行動が同じ場で重なった結果として、この時点で起こりうる出来事の候補を、渡す件数だけ挙げる。
日常の小さな、感情がぶつかる、偶発的な(事故・天候・病・思いがけない出会い)、居場所が変わる(旅立ち・帰還・避難)、
笑いや祝い、取り決めや対立が動くなど、種類の違うものを混ぜる。
各候補は当事者の人物像・性格と矛盾しない範囲で立てる。
出来事の種(この世界のほかの場面の筋から、時代・場所・固有名詞を抜いたもの)を渡したときは、候補は、この種のどれかをこの場所・この時点・この当事者に合わせて具体化したものか、直前・直近の出来事から連想したものにする。
この場所の直近の出来事の一覧(名前)と、人物・対象ごとに渡す直近の出来事(その者自身が場所を問わず関わった直近の出来事)を見て検討する。
同じ形容表現を繰り返し出来事の軸に据えない。

{_SITUATION_NOTE}"""

_RECORD_SYSTEM = f"""\
場所の状況、移動先の候補、サイコロで選ばれた出来事の候補を渡すので、その候補をこの場所にこの時点で起きた出来事として1件、記録に起こす。
候補の名前は event_name にそのまま使うか、整えてもよい。
character_ids には、関わった人物・対象の人物idを、居合わせる人物・対象の中からだけ選んで入れる(複数可)。
character_moves は、この出来事で住まい・拠点が変わった人物ごとの移動先(旅立ち・移住・避難・帰還など)。場所idは移動先の候補からだけ選ぶ。一時の外出は入れない。誰も変わっていなければ空にする。
この出来事が場所自身の改廃(消滅・新設)に及ぶときだけ、location_abolished / location_founded を埋める。
何も変わっていなければ location_abolished は false、location_founded は null のままにする。
location_founded の固有名詞は、書き方の名づけの基準で名づける。

event_text(出来事の本文):
選ばれた出来事の候補(名前と概要)を、当事者それぞれの人物像・性格・関係を土台にして記録に起こす。
候補の筋から外れない。本文では id ではなく名前で書く。

character_updates の text:
text は、この出来事を通して見えた、その人物の性格・信念・人となり(パーソナリティ。人物以外の対象なら性質・方針・立場)についてだけ短く一言で書く。
状況の要約や、その場の立場・置かれている状態は書かない。
この出来事でそれについて新しく分かったことが無ければ、この人物自体を character_updates に含めない。
既存の人物像と来歴で既に言われていることは、言い換えて書き足さない。硬い語・大げさな語で飾らず、普段の言葉で書く。
書いた内容は、この出来事の時刻の来歴に一文として積み足されるので、それだけで意味が通る一文にする。
この人物自身を指すときは名前を書かず、必ず「{NAME_PLACEHOLDER}」とだけ書く。

{_SITUATION_NOTE}"""


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
    decided = ai.generate(prompt, CandidatesDraft, system=_CANDIDATES_SYSTEM, style_scope=StyleScope.EVENT)
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
    draft = ai.generate(prompt, EventRecordDraft, system=_RECORD_SYSTEM, style_scope=StyleScope.EVENT)
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
