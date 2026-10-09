#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from data_access_logic.entrypoint import SessionEntrypoint
from data_access_logic.episode.mentions import cast_characters
from data_access_logic.episode_session.record import KnowerGap
from data_access_logic.history_start import by_start
from data_access_logic.material import Named
from db.schema import CharacterHistory, Episode, EpisodeCharacter
from db.stamp import Stamp


def _knows(history: CharacterHistory, character_id: int, time: Stamp) -> bool:
    return any(knower.knower_id == character_id and knower.start is not None and knower.start <= time
               for knower in history.knowers)


class ReadKnowerGaps(SessionEntrypoint):
    """話の登場人物の来歴のうち、話の時刻までに起きた行で、ほかの登場人物の名前が出るのに、その人物が話の時刻に知る相手に
    入っていない行を挙げる。人物役は知る相手の行しか読まないので、居合わせたはずの出来事を知らずに演じてしまう。
    名前が出ても居合わせたとは限らず、場所を知る相手にした行は見ないので、足すかは読んで決める(手番を回す前の確かめ)。"""

    def __init__(self, episode_id: int):
        self.episode_id = episode_id

    def execute(self, s: Session) -> list[KnowerGap]:
        episode = s.scalar(select(Episode).where(Episode.id == self.episode_id).options(
            selectinload(Episode.episode_characters).joinedload(EpisodeCharacter.character))
            .execution_options(populate_existing=True))
        if episode is None:
            raise ValueError(f"話 id={self.episode_id} が見つからない")
        time = episode.start
        if time is None:
            raise ValueError(f"話 id={self.episode_id} の時刻(start)が空")
        cast = [character for character in cast_characters(episode) if character.name]
        gaps = []
        for character in cast:
            for history in sorted((row for row in character.histories if row.covers(time)), key=by_start):
                unknowing = [Named.model_validate(other) for other in cast
                             if other.id != character.id and other.name in history.description
                             and not _knows(history, other.id, time)]
                if unknowing:
                    gaps.append(KnowerGap(history_id=history.id, character=character, start=history.start,
                                          description=history.description, unknowing=unknowing))
        return gaps
