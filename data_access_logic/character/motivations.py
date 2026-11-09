"""人物のモチベーション(`character_motivation`)を時刻で絞って読み、人物モードの裁いた増減を足す。

増減は行を直さず、足すことと `end` を付けることだけで表す(人物モードの書き手 `ai_append` でも書けるように)。
強さが変わったら、前の行を変わった時刻で終え、同じ内容で新しい強さの行を足す。
"""
from __future__ import annotations

import logging

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.character.record import MotivationChange
from db.schema import CharacterMotivation
from db.stamp import Stamp

logger = logging.getLogger(__name__)


def motivations_select(character_ids: list[int], time: Stamp | None) -> Select[CharacterMotivation]:
    """`time` に効いている行を強い順に。`time` を省けば、すべての行を始まりの新しい順に。"""
    query = select(CharacterMotivation).where(CharacterMotivation.character_id.in_(character_ids))
    if time is None:
        return query.order_by(CharacterMotivation.start.desc(), CharacterMotivation.id.desc())
    return (query.where(CharacterMotivation.start <= time,
                        (CharacterMotivation.end.is_(None)) | (CharacterMotivation.end > time))
            .order_by(CharacterMotivation.strength.desc(), CharacterMotivation.start.desc(),
                      CharacterMotivation.id.desc()))


def motivations_at(s: Session, character_id: int, time: Stamp) -> list[CharacterMotivation]:
    """材料に渡す、`time` に効いている本人の行(強い順に `constants.ACT_MOTIVATION_LIMIT` まで)。"""
    return list(s.scalars(motivations_select([character_id], time).limit(constants.ACT_MOTIVATION_LIMIT)).all())


def apply_changes(
    s: Session, changes: list[MotivationChange], character_ids: list[int], time: Stamp,
) -> list[CharacterMotivation]:
    """裁いた増減を `time` の行として書く。`character_ids` にいない人物と、`time` に効いていない行を指す増減は捨てる。
    足した行を返す。"""
    added = []
    ended_ids: set[int] = set()
    for change in changes:
        if change.character_id not in character_ids:
            logger.warning(f"モチベーションの増減: 居合わせない人物 id={change.character_id} を捨てた")
            continue
        previous = None
        if change.motivation_id is not None:
            previous = s.get(CharacterMotivation, change.motivation_id)
            if (previous is None or previous.character_id != change.character_id or not previous.covers(time)
                    or previous.id in ended_ids or previous.start == time):
                logger.warning(f"モチベーションの増減: id={change.motivation_id} は {time} に効いている"
                               f"人物 id={change.character_id} の行でないので捨てた")
                continue
        text = (change.text or "").strip() or (previous.text if previous is not None else "")
        if previous is None and (not text or not change.strength):
            logger.warning(f"モチベーションの増減: 内容か強さの無い新しい思いを捨てた(人物 id={change.character_id})")
            continue
        if previous is not None:
            if change.strength == previous.strength and text == previous.text:
                continue
            previous.end = time
            ended_ids.add(previous.id)
        if change.strength:
            row = CharacterMotivation(character_id=change.character_id, start=time, strength=change.strength, text=text)
            s.add(row)
            added.append(row)
    s.flush()
    return added
