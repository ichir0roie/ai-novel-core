#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.material import Material
from data_access_logic.query import common_query
from db.schema import (
    Character, CharacterHistoryCharacter, CharacterIdea, CharacterRelation, Episode, EpisodeCharacter,
    EpisodeCharacterSession, EventCharacter, IdeaHistoryCharacter,
)


class DeletedCharacter(Material):
    id: int
    name: str | None = None
    kind: str


class DeleteCharacter(CommitEntrypoint):
    """人物を消す。期間ごとの値・説明の変化・出自と居場所・相関・結んだアイデア・話に名前だけ出る行・
    来歴を知る人の行・話のセッションの行も消す。

    出来事の当事者か、話の登場人物・視点になっている人物は止まる(先に出来事・話から外す)。
    """

    model = Character

    def __init__(self, character_id: int):
        self.character_id = character_id

    def execute(self, s: Session) -> DeletedCharacter:
        record = common_query.get_row(s, Character, self.character_id)
        if s.scalars(select(EventCharacter.id).where(EventCharacter.character_id == record.id)).first() is not None:
            raise ValueError(f"character_id={record.id} は出来事の当事者になっている。先に出来事から外す")
        episode_id = s.scalars(select(Episode.id).where(or_(
            Episode.viewpoint_character_id == record.id,
            Episode.id.in_(select(EpisodeCharacter.episode_id).where(
                EpisodeCharacter.character_id == record.id, EpisodeCharacter.mentioned.is_(False)))))).first()
        if episode_id is not None:
            raise ValueError(f"character_id={record.id} は話 id={episode_id} の登場人物か視点になっている。先に話から外す")

        deleted = DeletedCharacter.model_validate(record)
        # 期間ごとの値・説明の変化・出自と居場所は selectin で読まれ、cascade で消える。それ以外は先に消す
        for model in (CharacterIdea, EpisodeCharacter, CharacterHistoryCharacter, IdeaHistoryCharacter,
                      EpisodeCharacterSession):
            s.execute(delete(model).where(model.character_id == record.id))
        s.execute(delete(CharacterRelation).where(or_(
            CharacterRelation.character_1_id == record.id, CharacterRelation.character_2_id == record.id)))
        s.delete(record)
        return deleted
