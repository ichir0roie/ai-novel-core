"""人物がある時刻に知ることのできるデータ(人物役が自分で読む材料)と、会った相手から見て分かること。

人物役には年の数を渡さない(作中の暦は db の年と桁が違い、年の数そのものが筋の外の手がかりになる)。
今の時刻は月日・時間帯・時で(「いま」)、物事の古さは、その時刻からの隔たりを人物の暦の単位一つで渡す(`time_sense.py`)。
来歴・履歴の行は隔たりと本文をつないだ一文(「3日前、〜」「2週間前、〜」「5年前、〜」)にし、持ち物・記憶・隠し事のような
今も続いている種別付きの行は「3年前から、持ち物: 〜」と言う。

- 人物の来歴(持ち物・記憶・隠し事も種別付きの行)・スキルの来歴・アイデアの履歴・場所の来歴は、知る相手(`KnowerMixin`)に
  当たる行だけ。知る相手が場所なら、その時刻にその場所(配下も含む)に住む人物が、知った時刻から知る。
- 行はその時刻までに起きたものだけ(人物・スキルの来歴は `end` を過ぎた行も外す)。期間・知った時刻の始まりが空の行
  (アイデアの履歴・関係・知る相手)は、いつからか決まっていないので渡さない。
- アイデア・スキルの本文と場所の説明(`text`)は作者だけが読むので渡さない。人物が知るのは、アイデアの履歴(作中の呼び名と
  受け止め方)、スキルの名前と来歴の行だけ。
- アイデアはすべて渡すと多すぎるので、はじめはプロットに名前(本質の名前か知っている呼び名)が出るものだけ。手番の要求に出た語は、
  人物役が `known_ideas_by_words` で引く。
- 装いは種別「装い」のスキルで持ち、見た人にそのまま知れるので、見た目(`skills.worn_at`)に入れ、スキルの一覧には入れない。
  物ごとに、物の名前(スキルの名前)・今の姿(効いている一番新しい行)・いつから身に着けているか(`skills.worn_since`)を渡す。
- 人物の範囲は本人と、その時刻に関係(`character_relation`)のある人物。本人には外見・芯・ミーム・行動原理・性格を、関係のある人物には
  外見と芯を渡し、plot はだれにも渡さない。話を渡したときは、関係のある人物の外見・芯・来歴をその話の登場人物・名前だけ出る人物の分だけ
  渡す(場にいない人物は関係の行の名前と間柄で足りる)。初対面の相手は、語り部が見た目(`appearance_of`)を差分で伝える。
- 本人が前の話の手番で言ったセリフ(`character_speech`)は、その時刻までに始まった話のもの(演じている話は除く)を、言ってからの
  人物の暦の日数で原文(`constants.SPEECH_VERBATIM_DAYS` 日まで)・鮮明(`SPEECH_VIVID_DAYS` 日まで)・あやふや(それより後)の
  どれか一つにして、話ごとに渡す。
- 本人が居合わせた出来事(`event_character` に本人がいる行)は、その時刻までのものを新しいほうから
  `constants.KNOWLEDGE_EVENT_LIMIT` 件、古い順に渡す。新しい `constants.KNOWLEDGE_EVENT_TEXT_COUNT` 件は本文で、それより前は要約で。
  話の外で人物が交わした会話(スキル `character-scenes`)を、話の中の人物役が覚えているようにするため。居合わせたので知る相手では絞らない。
- 本人のモチベーション(`character_motivation`)は、その時刻に効いている行と、もう終わった行を合わせて強い順に
  `constants.KNOWLEDGE_MOTIVATION_LIMIT` 件まで渡し、終わった行は昔のモチベーションに分ける。強さが変わっただけで終えた行は、
  同じ中身の効いている行があるので昔に入れない。本人の内心なので、知っている人物には渡さない。人物モードは別に渡す。
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import Field, model_serializer
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, contains_eager, joinedload, selectinload

from data_access_logic import constants
from data_access_logic.character import skills
from data_access_logic.character.cast import age_at, relations_at
from data_access_logic.character.models import CharacterParameterValues, CharacterRelationLine, personality_for_prompt
from data_access_logic.character.parameters import parameters_at
from data_access_logic.character.time_sense import TimeSense
from data_access_logic.history_start import by_start
from data_access_logic.idea.models import normalized
from data_access_logic.material import Material, Timestamp
from data_access_logic.query import common_query
from data_access_logic.query.period import dated_alive_at
from db.schema import (
    Character, CharacterHistory, CharacterMotivation, CharacterRelation, CharacterSkillHistory, CharacterSpeech, Episode,
    Event, IdeaHistory, IdeaHistoryKnower, KnowerMixin, LocationHistory, LocationHistoryKnower,
)
from db.stamp import Calendar, Stamp, active_calendar


@dataclass(frozen=True)
class Viewer:
    """知る側の人物と、その時刻に住む場所・そこから最上位までの場所。"""

    character_id: int
    time: Stamp
    location_ids: frozenset[int]


def knowing_time(s: Session, episode_id: int | None, time: Stamp | str | None) -> Stamp:
    """人物が知ることを読む時刻。渡された時刻、無ければ話の時刻。"""
    stamp = Stamp.parse(time)
    if stamp is not None:
        return stamp
    if episode_id is None:
        raise ValueError("話か時刻のどちらかが要る")
    start = common_query.get_row(s, Episode, episode_id).start
    if start is None:
        raise ValueError(f"話 id={episode_id} に時刻が無い")
    return start


def viewer_of(s: Session, character: Character, time: Stamp) -> Viewer:
    here = s.scalars(common_query.character_location_select(character.id, time)).first()
    home_id = here.location_id if here is not None else None
    location_ids = common_query.idea_scope_ids(s, home_id) if home_id is not None else []
    return Viewer(character_id=character.id, time=time, location_ids=frozenset(location_ids))


def knows(knowers: Sequence[KnowerMixin], viewer: Viewer) -> bool:
    """知った時刻の決まっていない相手は、まだ知らないものとする。"""
    return any(knower.start is not None and knower.start <= viewer.time
               and (knower.knower_id == viewer.character_id or knower.location_id in viewer.location_ids)
               for knower in knowers)


class KnownName(Material):
    name: str
    detail: str | None = None


class KnownHistory(Material):
    start: Timestamp | None = None
    # 人物の来歴の種別(装い・持ち物など)。スキル・場所の来歴には無い
    kind: str | None = None
    description: str


class KnownSkill(Material):
    name: str
    # 知っている来歴の行
    histories: list[KnownHistory]


class KnownPlace(Material):
    name: str | None = None
    # 知っている来歴の行
    histories: list[KnownHistory]


def known_histories(
    rows: Sequence[CharacterHistory | CharacterSkillHistory | LocationHistory], viewer: Viewer,
) -> list[KnownHistory]:
    known = [row for row in rows if row.covers(viewer.time) and knows(row.knowers, viewer)]
    return [KnownHistory.model_validate(row) for row in sorted(known, key=by_start)]


def _history_line(sense: TimeSense, now: Stamp, start: Stamp | None, description: str, kind: str | None = None) -> str:
    """隔たりと本文を一文につなぐ(「3日前、〜」)。種別付きの行は今も続いている物事なので、いつからかで言い、種別を本文の頭に付ける
    (「3年前から、持ち物: 〜」)。"""
    if start is None:
        return description if kind is None else f"{kind}: {description}"
    if kind is None:
        return f"{sense.ago(start, now)}、{description}"
    return f"{sense.since(start, now)}、{kind}: {description}"


def _histories_for_prompt(histories: list[KnownHistory], sense: TimeSense, now: Stamp) -> list[str]:
    return [_history_line(sense, now, history.start, history.description, history.kind) for history in histories]


def _skills_for_prompt(known: list[KnownSkill], sense: TimeSense, now: Stamp) -> list[dict[str, Any]]:
    return [{"名前": skill.name, "来歴(古い順)": _histories_for_prompt(skill.histories, sense, now)} for skill in known]


def _relations_for_prompt(relations: list[CharacterRelationLine], sense: TimeSense, now: Stamp) -> list[dict[str, Any]]:
    return [
        {"誰から": relation.character_1.name, "誰へ": relation.character_2.name, "関係": relation.relation,
         "説明": relation.text,
         "来歴(古い順)": [_history_line(sense, now, history.start, history.description) for history in relation.histories]}
        for relation in relations
    ]


class WornItem(Material):
    """身に着けている物一つ。"""

    # 物の名前(装いのスキルの名前)
    name: str
    # 今の姿(効いている一番新しい来歴の行の文)
    description: str
    # 身に着け始めた時刻(`skills.worn_since`)
    start: Timestamp | None = None


class AppearanceSerialized(Material):
    """会った相手から見て分かること(名前は入れない)。ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    kind: str
    age: int | None = None
    parameters: CharacterParameterValues
    # その時刻に身に着けている物(身に着けた順)
    outfit: list[WornItem] = []
    appearance: str | None = None
    # 見た時刻と、隔たりを数える暦(組み立てたときの文脈の暦。dump するときの文脈に左右されない)
    time: Stamp
    calendar: Calendar | None = Field(default_factory=active_calendar)

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        parameters, sense = self.parameters, TimeSense(self.calendar)
        return {"種別": self.kind, "年齢": self.age, "性別": parameters.sex, "背丈": parameters.height,
                "体格": parameters.build,
                "装い": [{"物": item.name, "姿": item.description,
                          "いつから": None if item.start is None else sense.ago(item.start, self.time)}
                         for item in self.outfit],
                "外見": self.appearance}


def appearance_of(s: Session, character: Character, time: Stamp) -> AppearanceSerialized:
    outfit = [WornItem(name=skill.name, description=rows[-1].description, start=skills.worn_since(skill, rows))
              for skill, rows in skills.worn_at(s, character, time)]
    return AppearanceSerialized(kind=character.kind, age=age_at(character, time),
                                parameters=parameters_at(character, time), outfit=outfit,
                                appearance=character.appearance, time=time)


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


class SpeechEpisode(Material):
    id: int
    start: Timestamp


class KnownSpeech(Material):
    verbatim: str
    vivid: str
    vague: str
    episode: SpeechEpisode


class KnownEvent(Material):
    name: str
    time: Timestamp
    location_name: str | None = None
    # 居合わせた人物の名前(本人も含む)
    characters: list[str]
    # 新しい出来事だけ本文、それより前は要約(要約がまだ無ければ空)
    text: str | None = None
    summary: str | None = None


class KnownMotivation(Material):
    id: int
    start: Timestamp
    # 終わった時刻。効いている行は空
    end: Timestamp | None = None
    strength: int
    text: str


def _strength(strength: int) -> str:
    return f"{strength}({constants.MOTIVATION_STRENGTHS.get(strength, '')})"


def _motivations_for_prompt(motivations: list[KnownMotivation], sense: TimeSense, now: Stamp,
                            ) -> dict[str, list[dict[str, Any]]]:
    """効いている行は、話の差分で指せるように id を付ける。終わった行は指して変えられないので id を付けない。"""
    return {
        "モチベーション(強い順)": [
            {"モチベーションid": motivation.id, "強さ": _strength(motivation.strength), "内容": motivation.text,
             "いつから": sense.ago(motivation.start, now)}
            for motivation in motivations if motivation.end is None],
        "昔のモチベーション(強い順)": [
            {"強さ": _strength(motivation.strength), "内容": motivation.text, "いつから": sense.ago(motivation.start, now),
             "いつ終わった": sense.ago(motivation.end, now)}
            for motivation in motivations if motivation.end is not None],
    }


def _events_for_prompt(events: list[KnownEvent], sense: TimeSense, now: Stamp) -> list[dict[str, Any]]:
    return [{"いつ": sense.ago(event.time, now), "名前": event.name, "場所": event.location_name,
             "居合わせた人物": event.characters,
             **({"本文": event.text} if event.text is not None else {"要約": event.summary})}
            for event in events]


def _speeches_for_prompt(speeches: list[KnownSpeech], sense: TimeSense, now: Stamp) -> list[dict[str, Any]]:
    """話ごとに、言ってからの人物の暦の日数で原文・鮮明・あやふやのどれか一つを渡す。"""
    by_episode: dict[int, list[KnownSpeech]] = {}
    for speech in speeches:
        by_episode.setdefault(speech.episode.id, []).append(speech)
    recalled: list[dict[str, Any]] = []
    for lines in by_episode.values():
        start = lines[0].episode.start
        days = sense.days(start, now)
        if days <= constants.SPEECH_VERBATIM_DAYS:
            recall, texts = "言ったとおりに覚えている", [line.verbatim for line in lines]
        elif days <= constants.SPEECH_VIVID_DAYS:
            recall, texts = "中身ははっきり覚えている", [line.vivid for line in lines]
        else:
            recall, texts = "おぼろげに覚えている", [line.vague for line in lines]
        recalled.append({"いつ": sense.ago(start, now), "覚え": recall, "セリフ": texts})
    return recalled


class KnowledgeSerialized(Material):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    time: Stamp
    me: KnownSelf
    # 本人の、その時刻の名字・口調など
    parameters: CharacterParameterValues
    relations: list[CharacterRelationLine]
    characters: list[KnownCharacter]
    ideas: list[KnownIdea]
    places: list[KnownPlace]
    # 本人が前の話で言ったセリフ(話の時刻・本文の順)。人物モードは台詞を書かせないので None にして、見出しごと出さない
    speeches: list[KnownSpeech] | None = None
    # 本人が居合わせた出来事(古い順)。人物モード(`expansion/acting.py`)は出来事を別に渡すので None にして、見出しごと出さない
    events: list[KnownEvent] | None = None
    # 本人のモチベーション(強い順。終わった行は `end` を持つ)。人物モードは別に渡すので None にして、見出しごと出さない
    motivations: list[KnownMotivation] | None = None
    # 今の時刻(「いま」)を出すか。人物モードは自分の材料の頭に出すので外す
    with_now: bool = True
    # 隔たりを数える暦(組み立てたときの文脈の暦。dump するときの文脈に左右されない)
    calendar: Calendar | None = Field(default_factory=active_calendar)

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        me, parameters, now, sense = self.me, self.parameters, self.time, TimeSense(self.calendar)
        events = {} if self.events is None else {
            "居合わせた出来事(古い順)": _events_for_prompt(self.events, sense, now)}
        motivations = {} if self.motivations is None else _motivations_for_prompt(self.motivations, sense, now)
        return {
            **({"いま": sense.now_for_prompt(now)} if self.with_now else {}),
            "自分": {
                "名前": me.name, **me.looks.model_dump(), "名字": parameters.family_name,
                "一人称": parameters.first_person, "二人称": parameters.second_person, "三人称": parameters.third_person,
                "口調": parameters.tone, "方言": parameters.dialect, "人物像": me.text, "ミーム": me.meme,
                "行動原理": me.principle, "性格": personality_for_prompt(parameters),
                "来歴(古い順)": _histories_for_prompt(me.histories, sense, now),
                "スキル": _skills_for_prompt(me.skills, sense, now),
                **({} if self.speeches is None else {"言ったセリフ(古い順)": _speeches_for_prompt(self.speeches, sense, now)}),
                **events,
                **motivations,
            },
            "関係": _relations_for_prompt(self.relations, sense, now),
            "知っている人物": [_character_for_prompt(character, sense, now) for character in self.characters],
            "知っているアイデア": [_idea_for_prompt(idea) for idea in self.ideas],
            "知っている場所": [{"名前": place.name, "来歴(古い順)": _histories_for_prompt(place.histories, sense, now)}
                         for place in self.places],
        }


def _character_for_prompt(character: KnownCharacter, sense: TimeSense, now: Stamp) -> dict[str, Any]:
    return {"名前": character.name, **character.looks.model_dump(), "人物像": character.text,
            "来歴(古い順)": _histories_for_prompt(character.histories, sense, now),
            "スキル": _skills_for_prompt(character.skills, sense, now)}


class KnownCharactersSerialized(Material):
    """知っている人物の外見・芯・来歴(本人が知る行だけ)。人物モードは、目の前に初めて来たときにだけ渡す。"""

    time: Stamp
    characters: list[KnownCharacter]
    calendar: Calendar | None = Field(default_factory=active_calendar)

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        sense = TimeSense(self.calendar)
        return {"人物": [_character_for_prompt(character, sense, self.time) for character in self.characters]}


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
        dated_alive_at(CharacterRelation, time)).order_by(CharacterRelation.id)).all()
    ids = [relation.character_2_id if relation.character_1_id == character.id else relation.character_1_id
           for relation in relations]
    return [id_ for id_ in dict.fromkeys(ids) if id_ != character.id]


def _skills(s: Session, character: Character, viewer: Viewer) -> list[KnownSkill]:
    """来歴の行を一つも知らないスキルは、持っていることも知らないので入れない。"""
    known = [KnownSkill(name=skill.name, histories=known_histories(skill.histories, viewer))
             for skill in skills.techniques_of(s, character.id)]
    return [skill for skill in known if skill.histories]


def _ideas(s: Session, viewer: Viewer, mentioned: Callable[[list[str]], bool]) -> list[KnownIdea]:
    """知っているアイデアのうち、本質の名前か知っている呼び名で `mentioned` に当たるもの。"""
    told = select(IdeaHistoryKnower.idea_history_id).where(or_(
        IdeaHistoryKnower.knower_id == viewer.character_id, IdeaHistoryKnower.location_id.in_(list(viewer.location_ids))))
    rows = s.scalars(
        select(IdeaHistory)
        .where(IdeaHistory.id.in_(told), dated_alive_at(IdeaHistory, viewer.time))
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


def _places(s: Session, viewer: Viewer) -> list[KnownPlace]:
    """知っている場所の来歴を、場所ごとに。知る相手に当たる行が一つも無い場所は入れない。"""
    told = select(LocationHistoryKnower.location_history_id).where(or_(
        LocationHistoryKnower.knower_id == viewer.character_id,
        LocationHistoryKnower.location_id.in_(list(viewer.location_ids))))
    rows = s.scalars(
        select(LocationHistory)
        .where(LocationHistory.id.in_(told))
        .options(joinedload(LocationHistory.location))
        .order_by(LocationHistory.location_id, LocationHistory.id)
        .execution_options(populate_existing=True)).all()
    by_location: dict[int, list[LocationHistory]] = {}
    for row in rows:
        by_location.setdefault(row.location_id, []).append(row)
    places = [KnownPlace(name=histories[0].location.name, histories=known_histories(histories, viewer))
              for histories in by_location.values()]
    return [place for place in places if place.histories]


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


def _speeches(s: Session, character_id: int, time: Stamp, acting_episode_id: int | None) -> list[KnownSpeech]:
    """`time` までに始まった話で言ったセリフ。演じている話のセリフは、本文を書き直すときに先回りになるので入れない。"""
    query = (select(CharacterSpeech).join(Episode, CharacterSpeech.episode_id == Episode.id)
             .where(CharacterSpeech.character_id == character_id, Episode.start.is_not(None), Episode.start <= time)
             # 話は id と時刻だけを使う。本文ごと引くと、セリフの数だけ本文を運んで遅い
             .options(contains_eager(CharacterSpeech.episode).load_only(Episode.id, Episode.start))
             .order_by(Episode.start, Episode.id, CharacterSpeech.position)
             .execution_options(populate_existing=True))
    if acting_episode_id is not None:
        query = query.where(Episode.id != acting_episode_id)
    return [KnownSpeech.model_validate(row) for row in s.scalars(query).all()]


def _events(s: Session, character_id: int, time: Stamp) -> list[KnownEvent]:
    """`time` までに本人が居合わせた出来事。古い順。"""
    rows = s.scalars(
        common_query.events_of_character_select(character_id, until=time, limit=constants.KNOWLEDGE_EVENT_LIMIT)
        .options(selectinload(Event.summary))
        .execution_options(populate_existing=True)).all()
    return [KnownEvent(name=row.name, time=row.time, location_name=None if row.location is None else row.location.name,
                       characters=[link.character.name for link in row.event_characters if link.character is not None],
                       text=row.text if index < constants.KNOWLEDGE_EVENT_TEXT_COUNT else None,
                       summary=None if row.summary is None else row.summary.text)
            for index, row in reversed(list(enumerate(rows)))]


def _motivations(s: Session, character_id: int, time: Stamp) -> list[KnownMotivation]:
    """`time` までに生まれた本人の行。強い順に、効いている行と終わった行を合わせて決まった件数まで。
    終わった行は、同じ中身の効いている行(強さが変わっただけ)か、もっと強い同じ中身の終わった行があれば外す。"""
    rows = s.scalars(
        select(CharacterMotivation)
        .where(CharacterMotivation.character_id == character_id, CharacterMotivation.start <= time)
        .order_by(CharacterMotivation.strength.desc(), CharacterMotivation.start.desc(), CharacterMotivation.id.desc())
    ).all()
    ended = {row.id for row in rows if row.end is not None and row.end <= time}
    seen = {row.text for row in rows if row.id not in ended}
    picked: list[KnownMotivation] = []
    for row in rows:
        if row.id in ended:
            if row.text in seen:
                continue
            seen.add(row.text)
        picked.append(KnownMotivation(id=row.id, start=row.start, end=row.end if row.id in ended else None,
                                      strength=row.strength, text=row.text))
        if len(picked) >= constants.KNOWLEDGE_MOTIVATION_LIMIT:
            break
    return picked


def knowledge_of(
    s: Session, character_id: int, time: Stamp, plot_text: str, scene_ids: set[int] | None,
    acting_episode_id: int | None, with_events: bool = False, with_motivations: bool = False, with_now: bool = True,
    with_speeches: bool = True,
) -> KnowledgeSerialized:
    """アイデアは、`plot_text` に名前の出るものだけを入れる。
    知っている人物(外見・芯・来歴)は、関係のある人物のうち `scene_ids`(話の登場人物・名前だけ出る人物)にいる人物だけ。
    ほかの関係のある人物は「関係」の名前と間柄だけで足りる。`scene_ids` が None なら(話を渡さないとき)関係のある人物すべて。
    言ったセリフは、`acting_episode_id`(演じている話)のものを除く。
    居合わせた出来事は `with_events`、本人のモチベーションは `with_motivations`、今の時刻は `with_now`、言ったセリフは
    `with_speeches` のときだけ入れる(人物モードは出来事・モチベーション・今の時刻を別に渡し、セリフは渡さない)。"""
    character = common_query.get_row(s, Character, character_id)
    viewer = viewer_of(s, character, time)
    other_ids = [id_ for id_ in _related_ids(s, character, time) if scene_ids is None or id_ in scene_ids]
    return KnowledgeSerialized(
        time=time,
        me=KnownSelf(name=character.name, looks=appearance_of(s, character, time),
                     text=character.text, meme=character.meme, principle=character.principle,
                     histories=known_histories(character.histories, viewer), skills=_skills(s, character, viewer)),
        parameters=parameters_at(character, time),
        relations=relations_at(s, [character], time, dated_alive_at),
        characters=_known_characters(s, viewer, other_ids, time),
        ideas=_ideas(s, viewer, _in_text(plot_text)),
        places=_places(s, viewer),
        speeches=_speeches(s, character_id, time, acting_episode_id) if with_speeches else None,
        events=_events(s, character_id, time) if with_events else None,
        motivations=_motivations(s, character_id, time) if with_motivations else None,
        with_now=with_now,
    )


def _known_characters(s: Session, viewer: Viewer, other_ids: list[int], time: Stamp) -> list[KnownCharacter]:
    # 一人ずつ引くと、人物の数だけ db を往復する
    by_id = {other.id: other for other in s.scalars(
        select(Character).where(Character.id.in_(other_ids)).options(selectinload(Character.histories))).all()}
    return [KnownCharacter(name=other.name, looks=appearance_of(s, other, time), text=other.text,
                           histories=known_histories(other.histories, viewer), skills=_skills(s, other, viewer))
            for other in (by_id[id_] for id_ in other_ids if id_ in by_id)]


def known_characters_of(s: Session, character_id: int, other_ids: list[int], time: Stamp) -> KnownCharactersSerialized:
    """`character_id` の人物が知っている、`other_ids` の人物の外見・芯・来歴(知る行だけ)。"""
    viewer = viewer_of(s, common_query.get_row(s, Character, character_id), time)
    return KnownCharactersSerialized(time=time, characters=_known_characters(s, viewer, other_ids, time))


def known_ideas_by_words(s: Session, character_id: int, time: Stamp, words: list[str]) -> KnownIdeasSerialized:
    """語ごとに、人物が知っているアイデアのうち名前の当たるもの。知らなければ空。"""
    viewer = viewer_of(s, common_query.get_row(s, Character, character_id), time)
    return KnownIdeasSerialized(words=[KnownIdeasOfWord(word=word, ideas=_ideas(s, viewer, _of_word(word)))
                                       for word in dict.fromkeys(words)])
