"""人物がある時刻に知ることのできるデータ(人物役が自分で読む材料)と、会った相手から見て分かること。

人物役には時刻・年を渡さない(作中の暦は db の年と桁が違い、年の数そのものが筋の外の手がかりになる)。
来歴の起きた年は、その時刻から何年前かで渡す。

人物の来歴・スキルの来歴・アイデアの履歴は、知る相手(`KnowerMixin` の行)に当たるものだけを渡す。知る相手が人物ならその人物、
場所ならその時刻にその場所(配下も含む)に住む人物が、知った時刻から知る。
アイデアの本文は本質で作者だけが読むので渡さない。人物が知るのはアイデアの履歴(作中の呼び名と受け止め方)の行だけ。
知っているアイデアをすべて渡すと多すぎるので、はじめに読むデータには、プロットに名前(本質の名前か知っている呼び名)が
出るものだけを入れる。手番の要求に出た語は、人物役が語で引いて(`known_ideas_by_words`)、知っているものだけを読む。
人物の来歴はその時刻までに起きた行だけ。
スキルの本文は本質で作者だけが読むので渡さない。人物が知るのは、スキルの名前と、その時刻までに起きたスキルの来歴の行のうち知っているものだけ。
人物の範囲は本人とその時刻に関係(`character_relation`)のある人物。関係の来歴もその時刻の年までに起きた行だけ。初対面の相手は、語り部が見た目(`appearance_of`)を差分で伝える。
本人には外見・芯・ミーム・行動原理を、関係のある人物には外見と芯を渡す。plot はだれにも渡さない。
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import model_serializer
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from data_access_logic.character.cast import age_at, relations_at
from data_access_logic.character.models import CharacterParameterValues, CharacterRelationLine
from data_access_logic.character.parameters import parameters_at
from data_access_logic.character import skills
from data_access_logic.idea.models import normalized
from data_access_logic.material import Material
from data_access_logic.query import common_query
from data_access_logic.query.period import alive_at
from db.schema import (
    Character, CharacterHistory, CharacterRelation, CharacterSkillHistory, IdeaHistory, IdeaHistoryKnower, KnowerMixin,
)
from db.stamp import Stamp


@dataclass(frozen=True)
class Viewer:
    """知る側の人物と、その時刻に住む場所・そこから最上位までの場所。"""

    character_id: int
    time: Stamp
    location_ids: frozenset[int]


def viewer_of(s: Session, character: Character, time: Stamp) -> Viewer:
    here = s.scalars(common_query.character_location_select(character.id, time)).first()
    home_id = here.location_id if here is not None else None
    location_ids = common_query.idea_scope_ids(s, home_id) if home_id is not None else []
    return Viewer(character_id=character.id, time=time, location_ids=frozenset(location_ids))


def knows(knowers: Sequence[KnowerMixin], viewer: Viewer) -> bool:
    return any((knower.start is None or knower.start <= viewer.time)
               and (knower.knower_id == viewer.character_id or knower.location_id in viewer.location_ids)
               for knower in knowers)


class KnownName(Material):
    name: str
    detail: str | None = None


class KnownHistory(Material):
    start: int | None = None
    description: str


class KnownSkill(Material):
    name: str
    # 知っている来歴の行
    histories: list[KnownHistory]


def known_histories(rows: Sequence[CharacterHistory | CharacterSkillHistory], viewer: Viewer) -> list[KnownHistory]:
    """本人か関係のある人物の来歴・スキルの来歴を渡す。古い順。"""
    known = [row for row in rows if row.covers(viewer.time) and knows(row.knowers, viewer)]
    return [KnownHistory.model_validate(row) for row in sorted(known, key=lambda row: row.start or 0)]


def _ago(start: int | None, year: int) -> str | None:
    """起きた年を、その時刻から何年前かで言う。"""
    if start is None:
        return None
    return "今年" if start == year else f"{year - start}年前"


def _histories_for_prompt(histories: list[KnownHistory], year: int) -> list[dict[str, Any]]:
    return [{"いつ": _ago(history.start, year), "来歴": history.description} for history in histories]


def _skills_for_prompt(known: list[KnownSkill], year: int) -> list[dict[str, Any]]:
    return [{"名前": skill.name, "来歴(古い順)": _histories_for_prompt(skill.histories, year)} for skill in known]


def _relations_for_prompt(relations: list[CharacterRelationLine], year: int) -> list[dict[str, Any]]:
    return [
        {"誰から": relation.character_1.name, "誰へ": relation.character_2.name, "関係": relation.relation,
         "説明": relation.text,
         "来歴(古い順)": [{"いつ": _ago(history.start, year), "来歴": history.description}
                         for history in relation.histories]}
        for relation in relations
    ]


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
    text: str | None = None
    meme: str | None = None
    principle: str | None = None
    histories: list[KnownHistory]
    skills: list[KnownSkill]


class KnownCharacter(Material):
    name: str | None = None
    looks: AppearanceSerialized
    text: str | None = None
    histories: list[KnownHistory]
    skills: list[KnownSkill]


class KnownIdea(Material):
    kind: str
    # 知っている履歴の行(作中の呼び名と受け止め方)
    names: list[KnownName]


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
        me, parameters, year = self.me, self.parameters, self.time.year
        return {
            "自分": {
                "名前": me.name, **me.looks.model_dump(), "名字": parameters.family_name,
                "一人称": parameters.first_person, "二人称": parameters.second_person, "三人称": parameters.third_person,
                "口調": parameters.tone, "方言": parameters.dialect, "人物像": me.text, "ミーム": me.meme,
                "行動原理": me.principle, "来歴(古い順)": _histories_for_prompt(me.histories, year),
                "スキル": _skills_for_prompt(me.skills, year),
            },
            "関係": _relations_for_prompt(self.relations, year),
            "知っている人物": [
                {"名前": character.name, **character.looks.model_dump(), "人物像": character.text,
                 "来歴(古い順)": _histories_for_prompt(character.histories, year),
                 "スキル": _skills_for_prompt(character.skills, year)}
                for character in self.characters],
            "知っているアイデア": [_idea_for_prompt(idea) for idea in self.ideas],
        }


def _idea_for_prompt(idea: KnownIdea) -> dict[str, Any]:
    return {"種別": idea.kind,
            "知っている呼び名": [{"呼び名": name.name, "受け止め方": name.detail} for name in idea.names]}


class KnownIdeasOfWord(Material):
    word: str
    ideas: list[KnownIdea]


class KnownIdeasSerialized(Material):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    words: list[KnownIdeasOfWord]

    @model_serializer
    def _for_prompt(self) -> list[dict[str, Any]]:
        return [{"語": word.word, "知っているアイデア": [_idea_for_prompt(idea) for idea in word.ideas]}
                for word in self.words]


def _related_ids(s: Session, character: Character, time: Stamp) -> list[int]:
    relations = s.scalars(select(CharacterRelation).where(
        or_(CharacterRelation.character_1_id == character.id, CharacterRelation.character_2_id == character.id),
        alive_at(CharacterRelation, time)).order_by(CharacterRelation.id)).all()
    ids = [relation.character_2_id if relation.character_1_id == character.id else relation.character_1_id
           for relation in relations]
    return [id_ for id_ in dict.fromkeys(ids) if id_ != character.id]


def _skills(s: Session, character: Character, viewer: Viewer) -> list[KnownSkill]:
    """来歴の行を一つも知らないスキルは、持っていることも知らないので入れない。"""
    known = [KnownSkill(name=skill.name, histories=known_histories(skill.histories, viewer))
             for skill in skills.skills_of(s, character.id)]
    return [skill for skill in known if skill.histories]


def _ideas(s: Session, viewer: Viewer, mentioned: Callable[[list[str]], bool]) -> list[KnownIdea]:
    """知っているアイデアのうち、本質の名前か知っている呼び名で `mentioned` に当たるもの。"""
    told = select(IdeaHistoryKnower.idea_history_id).where(or_(
        IdeaHistoryKnower.knower_id == viewer.character_id, IdeaHistoryKnower.location_id.in_(list(viewer.location_ids))))
    rows = s.scalars(
        select(IdeaHistory)
        .where(IdeaHistory.id.in_(told))
        .options(joinedload(IdeaHistory.idea))
        .order_by(IdeaHistory.idea_id, IdeaHistory.id)
        .execution_options(populate_existing=True)).all()
    known: dict[int, KnownIdea] = {}
    names: dict[int, list[str]] = {}
    for row in rows:
        if not knows(row.knowers, viewer):
            continue
        idea = known.setdefault(row.idea_id, KnownIdea(kind=row.idea.kind, names=[]))
        idea.names.append(KnownName.model_validate(row))
        names.setdefault(row.idea_id, [row.idea.name]).append(row.name)
    return [idea for idea_id, idea in known.items() if mentioned(names[idea_id])]


def _in_text(text: str) -> Callable[[list[str]], bool]:
    text = normalized(text)

    def mentioned(name: str) -> bool:
        name = normalized(name)
        return bool(name) and name in text
    return lambda names: any(mentioned(name) for name in names)


# 一字の名前は、ほかの語の一部に当たりすぎる
_MIN_NAME_LETTERS = 2


def _of_word(word: str) -> Callable[[list[str]], bool]:
    """語が名前の一部か、名前が語の一部なら当たる(「泥鰻の巣」で「泥鰻」、「鰻」で「泥鰻」)。"""
    word = normalized(word)

    def overlaps(name: str) -> bool:
        name = normalized(name)
        return bool(word and name) and (word in name or (len(name) >= _MIN_NAME_LETTERS and name in word))
    return lambda names: any(overlaps(name) for name in names)


def knowledge_of(s: Session, character_id: int, time: Stamp, plot_text: str) -> KnowledgeSerialized:
    """アイデアは、`plot_text` に名前の出るものだけを入れる。"""
    character = common_query.get_row(s, Character, character_id)
    viewer = viewer_of(s, character, time)
    others = [common_query.get_row(s, Character, id_) for id_ in _related_ids(s, character, time)]
    return KnowledgeSerialized(
        time=time,
        me=KnownSelf(name=character.name, looks=appearance_of(character, time),
                     text=character.text, meme=character.meme, principle=character.principle,
                     histories=known_histories(character.histories, viewer), skills=_skills(s, character, viewer)),
        parameters=parameters_at(character, time),
        relations=relations_at(s, [character], time),
        characters=[KnownCharacter(name=other.name, looks=appearance_of(other, time),
                                   text=other.text,
                                   histories=known_histories(other.histories, viewer), skills=_skills(s, other, viewer))
                    for other in others],
        ideas=_ideas(s, viewer, _in_text(plot_text)),
    )


def known_ideas_by_words(s: Session, character_id: int, time: Stamp, words: list[str]) -> KnownIdeasSerialized:
    """語ごとに、人物が知っているアイデアのうち名前の当たるもの。知らなければ空。"""
    viewer = viewer_of(s, common_query.get_row(s, Character, character_id), time)
    return KnownIdeasSerialized(words=[KnownIdeasOfWord(word=word, ideas=_ideas(s, viewer, _of_word(word)))
                                       for word in dict.fromkeys(words)])
