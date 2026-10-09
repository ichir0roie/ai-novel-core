#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from data_access_logic.character.skills import skills_of
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.material import Material
from data_access_logic.query import common_query
from db.schema import (
    Character, CharacterHistoryKnower, CharacterRelation, CharacterSkillHistoryKnower, Episode, EpisodeCharacter,
    EpisodeCharacterSession, EpisodeCharacterSessionWitness, EventCharacter, IdeaHistoryKnower, LocationHistoryKnower,
)


class DeletedCharacter(Material):
    id: int
    name: str | None = None
    kind: str


class DeleteCharacter(CommitEntrypoint):
    """人物を消す。期間ごとの値・説明の変化・出自と居場所・相関・スキル・話に名前だけ出る行・
    来歴を知る人の行・話のセッションの行も消す。

    出来事の当事者か、話の登場人物・視点になっている人物は止まる(先に出来事・話から外す)。
    """


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
        for model in (EpisodeCharacter, EpisodeCharacterSession, EpisodeCharacterSessionWitness):
            s.execute(delete(model).where(model.character_id == record.id))
        # 自分の来歴の知る人の行は cascade で消える。ほかの人物の来歴・スキルの来歴・アイデアの履歴の知る人に入った行は先に消す
        for knower_model in (CharacterHistoryKnower, CharacterSkillHistoryKnower, IdeaHistoryKnower, LocationHistoryKnower):
            s.execute(delete(knower_model).where(knower_model.knower_id == record.id))
        # スキルは人物から辿らない(`Character` にリレーションが無い)ので、来歴・知る相手の行ごと cascade で消えるよう一行ずつ消す
        for skill in skills_of(s, record.id):
            s.delete(skill)
        s.execute(delete(CharacterRelation).where(or_(
            CharacterRelation.character_1_id == record.id, CharacterRelation.character_2_id == record.id)))
        s.delete(record)
        return deleted
