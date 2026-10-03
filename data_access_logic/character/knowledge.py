"""人物がある時刻に知ることのできるデータ(人物役が自分で読む材料)と、会った相手から見て分かること。

本文・来歴は、知る相手(`KnowerMixin` の行)に当たるものだけを渡す。知る相手が人物ならその人物、場所ならその時刻に
その場所(配下も含む)に住む人物が、知った時刻から知る。アイデアは、効く場所と期間に住む人物も知る。来歴はその時刻までに起きた行だけ。
人物の範囲は本人とその時刻に関係(`character_relation`)のある人物。初対面の相手は、語り部が見た目(`appearance_of`)を差分で伝える。
本人には外見・芯・ミーム・行動原理を、関係のある人物には外見と、知っていれば芯を渡す。plot はだれにも渡さない。
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import model_serializer
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from data_access_logic.character.cast import age_at
from data_access_logic.character.models import CharacterParameterValues, CharacterRelationLine, relations_for_prompt
from data_access_logic.character.parameters import parameters_at
from data_access_logic.idea.alias import called
from data_access_logic.material import Material
from data_access_logic.query import common_query
from data_access_logic.query.period import alive_at
from db.schema import Character, CharacterHistory, CharacterRelation, Idea, IdeaHistory, IdeaKnower, KnowerMixin
from db.stamp import Stamp


@dataclass(frozen=True)
class Viewer:
    """知る側の人物と、その時刻に住む場所・そこから最上位までの場所。"""

    character_id: int
    time: Stamp
    home_id: int | None
    location_ids: frozenset[int]


def viewer_of(s: Session, character: Character, time: Stamp) -> Viewer:
    here = s.scalars(common_query.character_location_select(character.id, time)).first()
    home_id = here.location_id if here is not None else None
    location_ids = common_query.idea_scope_ids(s, home_id) if home_id is not None else []
    return Viewer(character_id=character.id, time=time, home_id=home_id, location_ids=frozenset(location_ids))


def knows(knowers: Sequence[KnowerMixin], viewer: Viewer) -> bool:
    return any((knower.start is None or knower.start <= viewer.time)
               and (knower.knower_id == viewer.character_id or knower.location_id in viewer.location_ids)
               for knower in knowers)


def _idea_known(idea: Idea, viewer: Viewer) -> bool:
    local = (idea.location_id in viewer.location_ids and (idea.start is None or idea.start <= viewer.time)
             and (idea.end is None or idea.end > viewer.time))
    return local or knows(idea.knowers, viewer)


class KnownHistory(Material):
    start: int | None = None
    description: str


def known_histories(rows: Sequence[CharacterHistory] | Sequence[IdeaHistory], viewer: Viewer) -> list[KnownHistory]:
    """古い順。"""
    known = [row for row in rows if row.covers(viewer.time) and knows(row.knowers, viewer)]
    return [KnownHistory.model_validate(row) for row in sorted(known, key=lambda row: row.start or 0)]


def _histories_for_prompt(histories: list[KnownHistory]) -> list[dict[str, Any]]:
    return [{"年": history.start, "来歴": history.description} for history in histories]


class AppearanceSerialized(Material):
    """会った相手から見て分かること(名前は入れない)。ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    kind: str
    age: int | None = None
    parameters: CharacterParameterValues
    appearance: str | None = None

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        parameters = self.parameters
        return {"種別": self.kind, "年齢": self.age, "性別": parameters.sex, "背丈": parameters.height,
                "体格": parameters.build, "外見": self.appearance}


def appearance_of(character: Character, time: Stamp) -> AppearanceSerialized:
    return AppearanceSerialized(kind=character.kind, age=age_at(character, time),
                                parameters=parameters_at(character, time), appearance=character.appearance)


class KnownSelf(Material):
    name: str | None = None
    looks: AppearanceSerialized
    # 本人も知らない芯(記憶を失った人物など)なら空
    text: str | None = None
    meme: str | None = None
    principle: str | None = None
    histories: list[KnownHistory]


class KnownCharacter(Material):
    name: str | None = None
    looks: AppearanceSerialized
    # 知らない芯なら空
    text: str | None = None
    histories: list[KnownHistory]


class KnownIdea(Material):
    name: str
    kind: str
    # その場所・時代での呼び名(当てはまる呼び名が無ければ空)
    called: str | None = None
    text: str
    histories: list[KnownHistory]


class KnowledgeSerialized(Material):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    time: Stamp
    me: KnownSelf
    # 本人の、その時刻の名字・口調など
    parameters: CharacterParameterValues
    relations: list[CharacterRelationLine]
    characters: list[KnownCharacter]
    ideas: list[KnownIdea]

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        me, parameters = self.me, self.parameters
        return {
            "時刻": str(self.time),
            "自分": {
                "名前": me.name, **me.looks.model_dump(), "名字": parameters.family_name,
                "一人称": parameters.first_person, "二人称": parameters.second_person, "三人称": parameters.third_person,
                "口調": parameters.tone, "方言": parameters.dialect, "人物像": me.text, "ミーム": me.meme,
                "行動原理": me.principle, "来歴(古い順)": _histories_for_prompt(me.histories),
            },
            "関係": relations_for_prompt(self.relations),
            "知っている人物": [
                {"名前": character.name, **character.looks.model_dump(), "人物像": character.text,
                 "来歴(古い順)": _histories_for_prompt(character.histories)}
                for character in self.characters],
            "知っているアイデア": [
                {"名前": idea.name, "呼び名": idea.called, "種別": idea.kind, "説明": idea.text,
                 "来歴(古い順)": _histories_for_prompt(idea.histories)}
                for idea in self.ideas],
        }


def _related_ids(s: Session, character: Character, time: Stamp) -> list[int]:
    relations = s.scalars(select(CharacterRelation).where(
        or_(CharacterRelation.character_1_id == character.id, CharacterRelation.character_2_id == character.id),
        alive_at(CharacterRelation, time)).order_by(CharacterRelation.id)).all()
    ids = [relation.character_2_id if relation.character_1_id == character.id else relation.character_1_id
           for relation in relations]
    return [id_ for id_ in dict.fromkeys(ids) if id_ != character.id]


def _ideas(s: Session, viewer: Viewer) -> list[KnownIdea]:
    local = s.scalars(common_query.ideas_select(viewer.location_ids, viewer.time)).all() if viewer.location_ids else []
    told = s.scalars(select(Idea).where(Idea.id.in_(
        select(IdeaKnower.idea_id).where(or_(IdeaKnower.knower_id == viewer.character_id,
                                             IdeaKnower.location_id.in_(viewer.location_ids)))))
                     .order_by(Idea.id)).all()
    ideas = [idea for idea in {idea.id: idea for idea in [*local, *told]}.values() if _idea_known(idea, viewer)]
    names = called(s, [idea.id for idea in ideas], viewer.home_id, viewer.time)
    return [
        KnownIdea(name=idea.name, kind=idea.kind, called=names[idea.id].name if idea.id in names else None,
                  text=idea.text, histories=known_histories(idea.histories, viewer))
        for idea in ideas
    ]


def knowledge_of(s: Session, character_id: int, time: Stamp) -> KnowledgeSerialized:
    character = common_query.get_row(s, Character, character_id)
    viewer = viewer_of(s, character, time)
    others = [common_query.get_row(s, Character, id_) for id_ in _related_ids(s, character, time)]
    knows_oneself = knows(character.knowers, viewer)
    return KnowledgeSerialized(
        time=time,
        me=KnownSelf(name=character.name, looks=appearance_of(character, time),
                     text=character.text if knows_oneself else None, meme=character.meme, principle=character.principle,
                     histories=known_histories(character.histories, viewer)),
        parameters=parameters_at(character, time),
        relations=[CharacterRelationLine.model_validate(row)
                   for row in s.execute(common_query.character_relations_at_select([character.id], time))],
        characters=[KnownCharacter(name=other.name, looks=appearance_of(other, time),
                                   text=other.text if knows(other.knowers, viewer) else None,
                                   histories=known_histories(other.histories, viewer))
                    for other in others],
        ideas=_ideas(s, viewer),
    )
