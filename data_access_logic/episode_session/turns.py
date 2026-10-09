"""話のセッションの手番。行動の入っていない一番古い要求の行の人物が、いま動く番。

終了の行(`closing`)と語りの行(人物の無い行)は手番に数えない。人物の次の行が終了の行なら、その人物の話は終わり。
人物役は自分の番に、前の自分の番から後の、自分が見聞きする語りとほかの人物の一手を、要求といっしょに受け取る。
"""
from __future__ import annotations

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from data_access_logic.episode_session.record import SessionRecord, TurnRecord, TurnState
from data_access_logic.query import common_query
from db.schema import Episode, EpisodeCharacterSession, EpisodeCharacterSessionWitness
from db.stamp import Stamp


def _pending() -> Select[EpisodeCharacterSession]:
    return (select(EpisodeCharacterSession)
            .where(EpisodeCharacterSession.action.is_(None))
            .order_by(EpisodeCharacterSession.id)
            .options(*SessionRecord.LOAD_OPTIONS)
            .execution_options(populate_existing=True))


def current_turn(s: Session, episode_id: int) -> EpisodeCharacterSession | None:
    return s.scalars(_pending().where(EpisodeCharacterSession.episode_id == episode_id,
                                      EpisodeCharacterSession.character_id.is_not(None),
                                      EpisodeCharacterSession.closing.is_(False))).first()


def _seen_line(row: EpisodeCharacterSession) -> str:
    if row.character is None:
        return row.request
    return f"{row.character.name}: {row.action}" + (f"「{row.speech}」" if row.speech else "")


def seen_lines(s: Session, record: EpisodeCharacterSession) -> list[str]:
    """`record` の人物が、前の自分の番から `record` までに見聞きした語りと、ほかの人物の一手(内心・狙いは入れない)。
    手番は id の順に回るので、前の番より手前の行は、前の番で受け取っている。"""
    session = EpisodeCharacterSession
    previous = s.scalar(select(func.max(session.id)).where(
        session.episode_id == record.episode_id, session.character_id == record.character_id,
        session.closing.is_(False), session.id < record.id))
    rows = s.scalars(session_select(record.episode_id).where(
        session.id > (previous or 0), session.id < record.id,
        or_(session.character_id.is_(None),
            and_(session.character_id != record.character_id, session.action.is_not(None))),
        session.witnesses.any(EpisodeCharacterSessionWitness.character_id == record.character_id))).all()
    return [_seen_line(row) for row in rows]


def turn_record(s: Session, record: EpisodeCharacterSession) -> TurnRecord:
    return TurnRecord(id=record.id, seen=[] if record.closing else seen_lines(s, record), request=record.request,
                      closing=record.closing)


def turn_of(s: Session, episode_id: int, character_id: int) -> TurnState:
    own = s.scalars(_pending().where(EpisodeCharacterSession.episode_id == episode_id,
                                     EpisodeCharacterSession.character_id == character_id)).first()
    if own is None:
        return TurnState(status="waiting")
    if own.closing:
        return TurnState(status="closed", record=turn_record(s, own))
    current = current_turn(s, episode_id)
    if current is not None and current.id == own.id:
        return TurnState(status="turn", record=turn_record(s, own))
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


def knowing_time(s: Session, character_id: int, episode_id: int | None, time: Stamp | str | None) -> Stamp:
    """人物が知ることを読む時刻。話があれば `actor_time`、無ければ渡された時刻。"""
    if episode_id is not None:
        return actor_time(s, episode_id, character_id)
    stamp = Stamp.parse(time)
    if stamp is None:
        raise ValueError("話か時刻のどちらかが要る")
    return stamp
