"""話のセッションの手番。行動の入っていない一番古い要求の行の人物が、いま動く番。

終了の行(`closing`)とイベントの行(`is_event`)は手番に数えない。人物の次の行が終了の行なら、その人物の話は終わり。
人物役には、番の行と一緒に、前の自分の番から見たイベントの行とほかの人物の一手を渡す。ほかの人物の内心・狙いは渡さない。
"""
from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from data_access_logic.character.knowledge import appearance_of, related_ids
from data_access_logic.episode_session.record import SeenSerialized, SessionRecord, TurnRecord, TurnState
from data_access_logic.query import common_query
from db.schema import Character, Episode, EpisodeCharacterSession
from db.stamp import Stamp


def _pending() -> Select[EpisodeCharacterSession]:
    return (select(EpisodeCharacterSession)
            .where(EpisodeCharacterSession.action.is_(None), EpisodeCharacterSession.is_event.is_(False))
            .order_by(EpisodeCharacterSession.id)
            .options(*SessionRecord.LOAD_OPTIONS)
            .execution_options(populate_existing=True))


def current_turn(s: Session, episode_id: int) -> EpisodeCharacterSession | None:
    return s.scalars(_pending().where(EpisodeCharacterSession.episode_id == episode_id,
                                      EpisodeCharacterSession.closing.is_(False))).first()


def turn_of(s: Session, episode_id: int, character_id: int) -> TurnState:
    own = s.scalars(_pending().where(EpisodeCharacterSession.episode_id == episode_id,
                                     EpisodeCharacterSession.character_id == character_id)).first()
    if own is None:
        return TurnState(status="waiting")
    if own.closing:
        return TurnState(status="closed", record=TurnRecord.model_validate(own))
    current = current_turn(s, episode_id)
    if current is not None and current.id == own.id:
        record = TurnRecord.model_validate(own)
        record.seen = _seen(s, own)
        return TurnState(status="turn", record=record)
    return TurnState(status="waiting")


def _seen(s: Session, own: EpisodeCharacterSession) -> list[SeenSerialized]:
    """前の自分の行からこの行までの、イベントの行とほかの人物の一手。初対面の相手は名前でなく見た目で渡す。"""
    assert own.character_id is not None
    previous = s.scalar(select(EpisodeCharacterSession.id)
                        .where(EpisodeCharacterSession.episode_id == own.episode_id,
                               EpisodeCharacterSession.character_id == own.character_id,
                               EpisodeCharacterSession.id < own.id)
                        .order_by(EpisodeCharacterSession.id.desc()))
    rows = s.scalars(session_select(own.episode_id).where(
        EpisodeCharacterSession.id > (previous or 0), EpisodeCharacterSession.id < own.id,
        EpisodeCharacterSession.is_event.is_(True)
        | ((EpisodeCharacterSession.character_id != own.character_id) & EpisodeCharacterSession.action.is_not(None)))).all()
    time = actor_time(s, own.episode_id, own.character_id)
    known = set(related_ids(s, common_query.get_row(s, Character, own.character_id), time))
    return [SeenSerialized(is_event=row.is_event, event=row.event) if row.character is None
            else SeenSerialized(is_event=False, action=row.action, speech=row.speech, event=row.event,
                                name=row.character.name if row.character.id in known else None,
                                looks=None if row.character.id in known else appearance_of(row.character, time))
            for row in rows]


def session_select(episode_id: int) -> Select[EpisodeCharacterSession]:
    return (select(EpisodeCharacterSession)
            .where(EpisodeCharacterSession.episode_id == episode_id)
            .order_by(EpisodeCharacterSession.id)
            .options(*SessionRecord.LOAD_OPTIONS)
            .execution_options(populate_existing=True))


def actor_time(s: Session, episode_id: int, character_id: int) -> Stamp:
    """人物役がいる時刻。その人物の時刻の入った一番新しい手番の行の時刻、無ければ話の時刻。"""
    time = s.scalar(select(EpisodeCharacterSession.time)
                    .where(EpisodeCharacterSession.episode_id == episode_id,
                           EpisodeCharacterSession.character_id == character_id,
                           EpisodeCharacterSession.time.is_not(None))
                    .order_by(EpisodeCharacterSession.id.desc()))
    if time is None:
        time = common_query.get_row(s, Episode, episode_id).start
    if time is None:
        raise ValueError(f"話 id={episode_id} に時刻が無い")
    return time
