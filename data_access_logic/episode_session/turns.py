"""話のセッションの手番。行動の入っていない一番古い要求の行の人物が、いま動く番。

終了の行(`closing`)と語りの行(人物の無い行)は手番に数えない。人物の次の行が終了の行なら、その人物の話は終わり。
作者の行(`author`)は人物の無い手番で、作者が書くまで後の手番を待たせる。人物役には届かない。
同時に動く手番(`simultaneous`)は、すぐ前の手番と組になる。組の手番は、まだ動いていないものすべてに一度に番が開く。
人物役は自分の番に、前の自分の番から後の、自分が見聞きする語りとほかの人物の一手を、要求といっしょに受け取る。
同じ組のほかの人物の一手は、同時に動いたので受け取らない(次の自分の番で受け取る)。
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


def _turn_rows(s: Session, episode_id: int) -> list[EpisodeCharacterSession]:
    """手番の行(人物の手番と作者の行。語りと終了の行は除く)を id の順に。"""
    return list(s.scalars(session_select(episode_id).where(
        or_(EpisodeCharacterSession.character_id.is_not(None), EpisodeCharacterSession.author.is_(True)),
        EpisodeCharacterSession.closing.is_(False))).all())


def _group_of(turns: list[EpisodeCharacterSession], index: int) -> list[EpisodeCharacterSession]:
    """`turns[index]` と同時に動く組(組でなければその行だけ)。"""
    start = index
    while start > 0 and turns[start].simultaneous:
        start -= 1
    end = index + 1
    while end < len(turns) and turns[end].simultaneous:
        end += 1
    return turns[start:end]


def current_turns(s: Session, episode_id: int) -> list[EpisodeCharacterSession]:
    """いま番の開いている行。一番古いまだ動いていない行と、それと同じ組のまだ動いていない行。"""
    turns = _turn_rows(s, episode_id)
    first = next((index for index, row in enumerate(turns) if row.action is None), None)
    if first is None:
        return []
    return [row for row in _group_of(turns, first) if row.action is None]


def current_turn(s: Session, episode_id: int) -> EpisodeCharacterSession | None:
    current = current_turns(s, episode_id)
    return current[0] if current else None


def simultaneous_ids(s: Session, record: EpisodeCharacterSession) -> set[int]:
    """`record` と同時に動く組のほかの行の id。"""
    turns = _turn_rows(s, record.episode_id)
    index = next((index for index, row in enumerate(turns) if row.id == record.id), None)
    if index is None:
        return set()
    return {row.id for row in _group_of(turns, index)} - {record.id}


def author_turn(s: Session, episode_id: int) -> EpisodeCharacterSession | None:
    """いまが作者の番なら、その作者の行。"""
    current = current_turn(s, episode_id)
    return current if current is not None and current.author else None


def author_session_running(s: Session, episode_id: int) -> bool:
    """作者の行があり、まだ閉じていないセッション(作者と語り部が本文を代わる代わる書いている)か。"""
    session = EpisodeCharacterSession
    rows = s.scalars(select(session.closing).where(
        session.episode_id == episode_id, or_(session.author.is_(True), session.closing.is_(True)))).all()
    return bool(rows) and not any(rows)


def write_author_line(s: Session, episode_id: int, text: str) -> EpisodeCharacterSession:
    """作者が書いたことを入れる。作者の番ならその行に、そうでなければ(語り部の番に口を挟んだ)作者の行を新しく足す。"""
    record = author_turn(s, episode_id)
    if record is None:
        record = EpisodeCharacterSession(episode_id=episode_id, author=True, request="")
        s.add(record)
    record.action = text
    return record


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
        session.author.is_(False),
        or_(session.character_id.is_(None),
            and_(session.character_id != record.character_id, session.action.is_not(None))),
        session.witnesses.any(EpisodeCharacterSessionWitness.character_id == record.character_id))).all()
    together = simultaneous_ids(s, record)
    return [_seen_line(row) for row in rows if row.id not in together]


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
    if own.id in {row.id for row in current_turns(s, episode_id)}:
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
