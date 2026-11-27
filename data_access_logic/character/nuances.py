"""人物の癖と思い込み(`character_nuance`)を時刻で絞って読み、人物モード・出来事の生成が見た増減を足す。"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from ai.instructions.naming import fill_name_placeholder
from db.schema import Character, CharacterNuance, NuanceKind
from db.stamp import Stamp

if TYPE_CHECKING:
    from data_access_logic.event.progress_models import NuanceChangeDraft

logger = logging.getLogger(__name__)


def nuances_select(character_id: int, time: Stamp | None) -> Select[CharacterNuance]:
    """`time` に効いている行を、癖 → 思い込みの順、始まりの古い順に。`time` を省けば、すべての行を同じ順に。"""
    query = select(CharacterNuance).where(CharacterNuance.character_id == character_id)
    if time is not None:
        query = query.where((CharacterNuance.start.is_(None)) | (CharacterNuance.start <= time),
                            (CharacterNuance.end.is_(None)) | (CharacterNuance.end > time))
    return query.order_by((CharacterNuance.kind != NuanceKind.HABIT.value), CharacterNuance.start.asc().nulls_first(),
                          CharacterNuance.id)


def nuances_at(s: Session, character_id: int, time: Stamp) -> list[CharacterNuance]:
    """`time` に効いている行。癖の相手の行も読む。"""
    return list(s.scalars(nuances_select(character_id, time).options(selectinload(CharacterNuance.target))
                          .execution_options(populate_existing=True)).all())


def check_nuance(record: CharacterNuance) -> None:
    if record.kind == NuanceKind.HABIT.value and not record.situation:
        raise ValueError("癖には場面(situation)を書く")
    if record.kind == NuanceKind.BELIEF.value and (record.situation or record.target_character_id is not None):
        raise ValueError("思い込みには場面(situation)も相手(target_character_id)も書かない")
    if record.target_character_id is not None and record.target_character_id == record.character_id:
        raise ValueError("癖の相手に本人は指せない")
    if record.start is not None and record.end is not None and record.end <= record.start:
        raise ValueError(f"end({record.end})は start({record.start})より後にする")


def apply_nuance_changes(
    s: Session, changes: list[NuanceChangeDraft], characters: dict[int, Character], time: Stamp,
) -> list[CharacterNuance]:
    """一日・出来事で新しく見えた・変わった癖と思い込みを `time` の行として書く。`characters`(居合わせた人物)にいない人物の行と、
    今ある行と同じ中身の行は捨てる。変わった行は、前の行を `time` で終えて、変わった後の行を足す(行は直さずに積む)。足した行を返す。"""
    added: list[CharacterNuance] = []
    for change in changes:
        character = characters.get(change.character_id)
        if character is None or not change.text:
            logger.warning(f"癖・思い込み: 居合わせない人物 id={change.character_id} か、中身の空の行を捨てた")
            continue
        habit = change.kind == NuanceKind.HABIT
        if habit and not change.situation:
            logger.warning(f"癖・思い込み: 場面の無い癖を捨てた(人物 id={change.character_id})")
            continue
        target_id = change.target_character_id if habit else None
        if target_id is not None and (target_id not in characters or target_id == character.id):
            target_id = None
        text = fill_name_placeholder(change.text, character.name or "")
        situation = fill_name_placeholder(change.situation, character.name or "") if habit else None
        current = nuances_at(s, character.id, time)
        if any(row.text == text for row in current):
            continue
        previous = next((row for row in current if row.id == change.replaces_nuance_id), None)
        if change.replaces_nuance_id is not None and previous is None:
            logger.warning(f"癖・思い込み: id={change.replaces_nuance_id} は {time} に効いている"
                           f"人物 id={character.id} の行でないので、新しい行として足す")
        if previous is not None:
            previous.end = time
        row = CharacterNuance(character_id=character.id, kind=change.kind.value, situation=situation,
                              target_character_id=target_id, text=text, start=time)
        s.add(row)
        added.append(row)
    s.flush()
    return added
