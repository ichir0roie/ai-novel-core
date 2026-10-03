"""話のセッションの手番。行動の入っていない一番古い要求の行の人物が、いま動く番。

終了の行(`closing`)は手番に数えない。人物の次の行が終了の行なら、その人物の話は終わり。
"""
from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from data_access_logic.episode_session.record import SessionRecord, TurnRecord, TurnState
from data_access_logic.query import common_query
from db.schema import Episode, EpisodeCharacterSession
from db.stamp import Stamp


def _pending() -> Select[EpisodeCharacterSession]:
    return (select(EpisodeCharacterSession)
            .where(EpisodeCharacterSession.action.is_(None))
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
        return TurnState(status="turn", record=TurnRecord.model_validate(own))
    return TurnState(status="waiting")


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
