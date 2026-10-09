#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint, record_of
from data_access_logic.episode_session.form import TurnRequest
from data_access_logic.episode_session.record import SessionRecord
from data_access_logic.episode_session.stage import acquaintances
from db.schema import Character, Episode, EpisodeCharacter, EpisodeCharacterSession, EpisodeCharacterSessionWitness


class AddTurns(CommitEntrypoint):
    """語り部が、話のセッションに手番の要求の行を並べた順に足す。人物役は自分の行が来たら行動を入れる。

    `narration` を渡すと、その場の何人もに見える・聞こえる状況を語りの行として手番の前に一つだけ足し、
    `witness_ids` の人物それぞれの次の番で届ける。手番の人物の一手も、見聞きする人物(手番の `witness_ids`、
    空なら `witness_ids`)の次の番で届く。一手には名前が付くので、届けるのは知り合い(語り部の材料の「知り合い」)にだけ。
    """


    def __init__(self, episode_id: int, turns: list[TurnRequest], narration: str | None = None,
                 witness_ids: list[int] | None = None):
        self.episode_id = episode_id
        self.turns = turns
        self.narration = narration
        self.witness_ids = witness_ids or []

    def execute(self, s: Session) -> list[SessionRecord]:
        self.check_exists(s, Episode, self.episode_id, "episode_id")
        if self.narration is not None and not self.narration.strip():
            raise ValueError("narration が空")
        if not self.turns and self.narration is None:
            raise ValueError("turns か narration のどちらかが要る")
        if self.narration is not None and not self.witness_ids:
            raise ValueError("narration には、見聞きする人物(witness_ids)が要る")
        cast_ids = set(s.scalars(select(EpisodeCharacter.character_id).where(
            EpisodeCharacter.episode_id == self.episode_id, EpisodeCharacter.mentioned.is_(False))).all())
        for character_id in {*self.witness_ids, *(id_ for turn in self.turns for id_ in turn.witness_ids or [])}:
            if character_id not in cast_ids:
                raise ValueError(f"witness_ids の人物 id={character_id} は話 id={self.episode_id} の登場人物でない")

        rows = []
        if self.narration is not None:
            rows.append(EpisodeCharacterSession(
                episode_id=self.episode_id, time=self.turns[0].time if self.turns else None, request=self.narration,
                witnesses=[EpisodeCharacterSessionWitness(character_id=id_) for id_ in dict.fromkeys(self.witness_ids)]))
        known = acquaintances(s, self.episode_id) if any(self._witnesses_of(turn) for turn in self.turns) else set()
        for turn in self.turns:
            self.check_exists(s, Character, turn.character_id, "character_id")
            witnesses = self._witnesses_of(turn)
            for witness_id in witnesses:
                if frozenset((turn.character_id, witness_id)) not in known:
                    raise ValueError(
                        f"人物 id={witness_id} は人物 id={turn.character_id} と知り合いでないので、名前の付いた一手を届けられない。"
                        "その人物の一手は、見て分かる言葉で語り(narration)か要求に書く")
            row = EpisodeCharacterSession(
                episode_id=self.episode_id,
                witnesses=[EpisodeCharacterSessionWitness(character_id=id_) for id_ in witnesses])
            turn.write_to(row)
            rows.append(row)

        records = []
        for row in rows:
            s.add(row)
            self.finalize(s, row)
            records.append(record_of(s, SessionRecord, row))
        return records

    def _witnesses_of(self, turn: TurnRequest) -> list[int]:
        return [id_ for id_ in dict.fromkeys(self.witness_ids if turn.witness_ids is None else turn.witness_ids)
                if id_ != turn.character_id]
