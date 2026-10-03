"""人物がある時刻に知ることのできるデータ(人物役が自分で読む材料)。

本文(人物の芯・アイデアの説明)と来歴は、公開のものと、その人物が知る人に入った非公開のものだけを渡す。来歴はその時刻までに起きた行だけ。
人物の範囲は本人とその時刻に関係(`character_relation`)のある人物(初対面の相手は、語り部が状況の差分で伝える)。
アイデアの範囲は本人に結んだアイデアと居場所に効くアイデアで、本文を知らないアイデアは名前ごと渡さない。
"""
from __future__ import annotations

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
from data_access_logic.source_text import without_plot_section
from db.schema import Character, CharacterHistory, CharacterIdea, CharacterRelation, Idea, IdeaHistory, Visibility
from db.stamp import Stamp

_VISIBILITY_LABELS = {Visibility.PUBLIC: "公開", Visibility.PRIVATE: "秘密"}


def knows(row: Character | Idea | CharacterHistory | IdeaHistory, character_id: int) -> bool:
    return row.visibility == Visibility.PUBLIC or character_id in row.knower_ids


def _text_known(row: Character, character_id: int) -> str | None:
    return without_plot_section(row.text) if knows(row, character_id) else None


class KnownHistory(Material):
    start: int | None = None
    visibility: Visibility
    description: str


def known_histories(rows: list[CharacterHistory] | list[IdeaHistory], character_id: int, time: Stamp) -> list[KnownHistory]:
    """古い順。"""
    known = [row for row in rows if row.covers(time) and knows(row, character_id)]
    return [KnownHistory.model_validate(row) for row in sorted(known, key=lambda row: row.start or 0)]


def _histories_for_prompt(histories: list[KnownHistory]) -> list[dict[str, Any]]:
    return [{"年": history.start, "公開度": _VISIBILITY_LABELS[history.visibility], "来歴": history.description}
            for history in histories]


class KnownSelf(Material):
    name: str | None = None
    kind: str
    # 人物の芯から `# plot` の節を除いたもの。本人も知らない本文なら空
    text: str | None = None
    age: int | None = None
    parameters: CharacterParameterValues
    histories: list[KnownHistory]


class KnownCharacter(Material):
    name: str | None = None
    kind: str
    # 人物の芯から `# plot` の節を除いたもの。知らない本文なら空
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
    relations: list[CharacterRelationLine]
    characters: list[KnownCharacter]
    ideas: list[KnownIdea]

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        me, parameters = self.me, self.me.parameters
        return {
            "時刻": str(self.time),
            "自分": {
                "名前": me.name, "種別": me.kind, "年齢": me.age, "名字": parameters.family_name, "性別": parameters.sex,
                "背丈": parameters.height, "体格": parameters.build, "一人称": parameters.first_person,
                "二人称": parameters.second_person, "三人称": parameters.third_person, "口調": parameters.tone,
                "方言": parameters.dialect, "人物像": me.text, "来歴(古い順)": _histories_for_prompt(me.histories),
            },
            "関係": relations_for_prompt(self.relations),
            "知っている人物": [
                {"名前": character.name, "種別": character.kind, "人物像": character.text,
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


def _ideas(s: Session, character: Character, time: Stamp) -> list[KnownIdea]:
    here = s.scalars(common_query.character_location_select(character.id, time)).first()
    local: list[Idea] = []
    if here is not None:
        local = list(s.scalars(common_query.ideas_select(common_query.idea_scope_ids(s, here.location_id), time)).all())
    local_ids = {idea.id for idea in local}
    linked = s.scalars(select(Idea).join(CharacterIdea, CharacterIdea.idea_id == Idea.id)
                       .where(CharacterIdea.character_id == character.id, Idea.id.not_in(local_ids))
                       .order_by(Idea.id)).all()
    ideas = [idea for idea in [*local, *linked] if knows(idea, character.id)]
    names = called(s, [idea.id for idea in ideas], here.location_id if here is not None else None, time)
    return [
        KnownIdea(name=idea.name, kind=idea.kind, called=names[idea.id].name if idea.id in names else None,
                  text=idea.text, histories=known_histories(idea.histories, character.id, time))
        for idea in ideas
    ]


def knowledge_of(s: Session, character_id: int, time: Stamp) -> KnowledgeSerialized:
    character = common_query.get_row(s, Character, character_id)
    others = [common_query.get_row(s, Character, id_) for id_ in _related_ids(s, character, time)]
    return KnowledgeSerialized(
        time=time,
        me=KnownSelf(name=character.name, kind=character.kind, text=_text_known(character, character.id),
                     age=age_at(character, time), parameters=parameters_at(character, time),
                     histories=known_histories(character.histories, character.id, time)),
        relations=[CharacterRelationLine.model_validate(row)
                   for row in s.execute(common_query.character_relations_at_select([character.id], time))],
        characters=[KnownCharacter(name=other.name, kind=other.kind, text=_text_known(other, character.id),
                                   histories=known_histories(other.histories, character.id, time))
                    for other in others],
        ideas=_ideas(s, character, time),
    )
