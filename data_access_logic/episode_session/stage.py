"""語り部(エージェント `narrator`)が手番を回すときに読む材料。

話のプロット・時刻、場所、登場人物とその来歴、登場人物どうしの関係とその来歴、話に結んだ設定とその履歴を渡す。
作者の目で読むので、芯・来歴・履歴は知る相手に関わらずすべてを渡し、非公開かどうかと誰が知っているかを添える
(語り部は、知らない人物に状況の差分で漏らさないのに使う)。前の話・本文は渡さない。人物がこれまでに何をしたかは、
人物役が自分の知ることのできるデータ(`character/knowledge.py`)から動いて出す。本文は手番を終えたあと、
本体の Claude が本文の材料(`episode/brief.py`)を読んで書く。
"""
from __future__ import annotations

from typing import Any

from pydantic import model_serializer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from data_access_logic.character.cast import age_at, relations_at, secrets_at
from data_access_logic.character.models import (
    CharacterMaterial, CharacterRelationLine, CharacterSecrets, relations_for_prompt, secrets_for_prompt,
)
from data_access_logic.character.parameters import parameters_at
from data_access_logic.episode.mentions import cast_characters
from data_access_logic.idea.links import linked_ideas_at
from data_access_logic.idea.models import LinkedIdeaMaterial, linked_idea_for_prompt
from data_access_logic.location.models import LocationMaterial, LocationTextMaterial
from data_access_logic.material import Material, Timestamp
from data_access_logic.query import common_query
from db.schema import Episode, EpisodeCharacter, Location


class StageEpisode(Material):
    id: int
    start: Timestamp
    plot_text: str


class StageMember(Material):
    character: CharacterMaterial
    age: int | None = None
    sex: str | None = None
    secrets: CharacterSecrets


class Stage(Material):
    main_episode: StageEpisode
    # 話の場所(無ければ作品の立つ場所)とその親。広い順
    locations: list[LocationMaterial]
    location: LocationTextMaterial | None = None
    cast: list[StageMember]
    # 両側とも登場人物で、話の時刻に続いている関係(来歴はその年までに起きた行)。初対面かどうかを語り部が見分ける
    relations: list[CharacterRelationLine]
    # 話に結んだアイデア。呼び名は話の時刻・場所に効く履歴から。履歴の行はすべて添える
    ideas: list[LinkedIdeaMaterial]


class StageSerialized(Stage):
    # 語り部は人物 id で手番を足し、時刻を手番の行に入れるので、id と時刻を残す
    @model_serializer
    def _for_narrator(self) -> dict[str, Any]:
        episode = self.main_episode
        return {
            "この話": {"話id": episode.id, "時刻": str(episode.start), "プロット": episode.plot_text},
            "場所(広い順)": [location.name for location in self.locations],
            "場所の説明": None if self.location is None else self.location.text,
            "登場人物": [{"人物id": member.character.id, "名前": member.character.name, "年齢": member.age,
                      "性別": member.sex, "外見": member.character.appearance, "人物像": member.character.text,
                      **secrets_for_prompt(member.secrets)}
                     for member in self.cast],
            "登場人物どうしの関係": relations_for_prompt(self.relations),
            "関係する設定": [linked_idea_for_prompt(linked) for linked in self.ideas],
        }


def stage_of(s: Session, episode_id: int) -> StageSerialized:
    episode = s.scalar(
        select(Episode)
        .where(Episode.id == episode_id)
        .options(
            joinedload(Episode.story),
            selectinload(Episode.episode_characters).joinedload(EpisodeCharacter.character),
        )
        .execution_options(populate_existing=True)
    )
    if episode is None:
        raise ValueError(f"話 id={episode_id} が見つからない")
    time = episode.start
    if time is None:
        raise ValueError(f"話 id={episode_id} の時刻(start)が空")
    location_id = episode.location_id or episode.story.location_id
    characters = cast_characters(episode)
    cast_ids = {character.id for character in characters}
    relations = [line for line in relations_at(s, characters, time)
                 if line.character_1.id in cast_ids and line.character_2.id in cast_ids]
    return StageSerialized(
        main_episode=episode,
        locations=common_query.location_path(s, location_id) if location_id is not None else [],
        location=s.get(Location, location_id) if location_id is not None else None,
        cast=[StageMember(character=character, age=age_at(character, time), sex=parameters_at(character, time).sex,
                          secrets=secrets_at(s, character, time))
              for character in characters],
        relations=relations,
        ideas=linked_ideas_at(s, episode, location_id, time),
    )
