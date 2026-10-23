"""語り部(話を書くセッションの Claude)が手番を回すときに読む材料。

語り部の受け持ちはプロットと場所・時刻と人物の表層なので、話のプロット・時刻、場所、登場人物の外から見て分かること
(名前・年齢・性別・体格・装い・外見)と、登場人物のだれとだれが知り合いか(関係の名前だけ)を渡す。装いは、話の時刻に効いている装いのスキルの来歴の行(身に着けている物ごと)。
人物の芯・来歴(持ち物・記憶・隠し事の行も含む)、関係の説明・来歴、設定(アイデア)、前の話・本文は渡さない。人物の内側と、人物がこれまでに何をしたかは、
人物役が自分の知ることのできるデータ(`character/knowledge.py`)から動いて出す。
本文は手番を終えたあと、本体の Claude が本文の材料(`episode/brief.py`)を読んで書く。
"""
from __future__ import annotations

from typing import Any

from pydantic import model_serializer
from sqlalchemy.orm import Session

from data_access_logic.character.cast import age_at, relations_at
from data_access_logic.character.skills import outfit_at
from data_access_logic.character.models import CharacterMaterial, CharacterParameterValues, CharacterRelationLine
from data_access_logic.character.parameters import parameters_at
from data_access_logic.episode.material import load_episode
from data_access_logic.episode.mentions import cast_characters
from data_access_logic.history_start import start_for_prompt
from data_access_logic.location.models import LocationLine, LocationMaterial
from data_access_logic.location.reading import location_at
from data_access_logic.material import Material, Timestamp
from data_access_logic.query import common_query
from data_access_logic.query.period import dated_alive_at
from db.schema import Location


class StageEpisode(Material):
    id: int
    start: Timestamp
    plot_text: str


class StageMember(Material):
    character: CharacterMaterial
    age: int | None = None
    # 話の時刻の値
    parameters: CharacterParameterValues
    # 話の時刻に効いている装いの行(身に着けている物ごと)
    outfit: list[str] = []


class Stage(Material):
    main_episode: StageEpisode
    # 話の場所とその親。広い順
    locations: list[LocationMaterial]
    # 来歴は話の時刻の年まで
    location: LocationLine | None = None
    cast: list[StageMember]
    # 両側とも登場人物で、話の時刻に続いている関係。初対面かどうかを語り部が見分ける
    relations: list[CharacterRelationLine]


class StageSerialized(Stage):
    # 語り部は人物 id で手番を足し、時刻を手番の行に入れるので、id と時刻を残す
    @model_serializer
    def _for_narrator(self) -> dict[str, Any]:
        episode = self.main_episode
        return {
            "この話": {"話id": episode.id, "時刻": str(episode.start), "プロット": episode.plot_text},
            "場所(広い順)": [location.name for location in self.locations],
            "場所の説明": None if self.location is None else self.location.text,
            "場所の来歴(古い順)": [] if self.location is None else [
                f"{start_for_prompt(history.start)}: {history.description}" for history in self.location.histories],
            "登場人物": [{"人物id": member.character.id, "名前": member.character.name, "年齢": member.age,
                      "性別": member.parameters.sex, "体格": member.parameters.build,
                      "装い": member.outfit, "外見": member.character.appearance}
                     for member in self.cast],
            # 人物 id の組は、一手を届ける相手が知り合いかを手番のファイルで確かめるのに写す(`episode_session/store.py`)
            "知り合い": [{"人物id": [relation.character_1.id, relation.character_2.id], "誰から": relation.character_1.name,
                      "誰へ": relation.character_2.name, "関係": relation.relation}
                     for relation in self.relations],
        }


def stage_of(s: Session, episode_id: int) -> StageSerialized:
    episode = load_episode(s, episode_id)
    time = episode.start
    if time is None:
        raise ValueError(f"話 id={episode_id} の時刻(start)が空")
    location_id = episode.location_id
    characters = cast_characters(episode)
    cast_ids = {character.id for character in characters}
    return StageSerialized(
        main_episode=episode,
        locations=common_query.location_path(s, location_id) if location_id is not None else [],
        location=location_at(common_query.get_row(s, Location, location_id), time) if location_id is not None else None,
        cast=[StageMember(character=character, age=age_at(character, time), parameters=parameters_at(character, time),
                          outfit=outfit_at(s, character, time))
              for character in characters],
        relations=[line for line in relations_at(s, characters, time, dated_alive_at)
                   if line.character_1.id in cast_ids and line.character_2.id in cast_ids],
    )
