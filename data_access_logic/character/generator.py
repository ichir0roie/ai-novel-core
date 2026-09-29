#!/usr/bin/env python3
"""人物・人物以外の対象(国・組織・集団・物)を一件生む。中身(説明・年齢・口調)→ 設定を踏まえた清書 → 名付け、の順に AI に決めさせる。

名前は中身が決まったあとに、その内容から連想して決める。生んだ人物は `confirmed=未確認` で足す。
"""
from __future__ import annotations

import random

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ai.instructions.idea_context import IDEA_CONTEXT_INSTRUCTION
from ai.instructions.naming import (
    CHARACTER_NAMING_INSTRUCTION, IDEA_NAMING_INSTRUCTION, NAME_PLACEHOLDER, fill_name_placeholder,
)
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.form import CharacterForm
from data_access_logic.character.generator_models import (
    BirthPlaceMaterial, CharacterBirthMaterialSerialized, CharacterNameMaterialSerialized, HistoryItemDraft,
    NameDraft, NonPersonContentDraft, PersonContentDraft, PersonNameDraft, PolishDraft, PolishRequestSerialized,
    StoryElementsDraft, StoryElementsRequestSerialized,
)
from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.character.parameters import overlay, parameter_row, parameters_at, rolled, without_person_values
from data_access_logic.idea.context import gather_ideas
from data_access_logic.idea.links import link
from data_access_logic.idea.models import IdeaMaterial
from data_access_logic.meme.extractor import draw, position_legend
from data_access_logic.meme.models import DrawnMeme
from data_access_logic.query import common_query, dictionary_query, story_createion_query
from db.schema import CHARACTER_KIND_PERSON, PERSONALITY_LEVELS, Character, CharacterPlace, ConfirmStatus, Location
from db.stamp import Stamp

_PLACEHOLDER_INSTRUCTION = (
    f"この一件の名前はまだ決まっていない。説明の中でこの一件を指すときは必ず「{NAME_PLACEHOLDER}」と書き、名前を考案して書き込まない。"
)

_LATER_INSTRUCTION = (
    "筋書きや既にいる人物・対象の説明は、現在の時刻より後の姿で書かれていることがある。"
    "「この時刻より後に始まる設定(まだ無い)」を渡したときは、それはまだ世に無い。その設定に当たる立場・仕事・組織・技術・出来事を、"
    "来歴にも現在の姿にも出さず、既にいる人物の説明に出てきても、この時刻にはまだ無いものとして扱う。"
)

_MATERIAL_INSTRUCTION = """\
材料は日本語の見出しを付けた JSON で渡す。
「決まっている」の値が null でなければ、その値をそのまま使う。
「作者の指定」は核にする。足りないところを補い、言い回しは変えてよい。"""


def _meme_instruction(subject: str) -> str:
    return (
        f"「行動原理(ミーム)」を渡したときは、それぞれに振られた古今表裏({position_legend()})を変えずに、"
        f"ミームどうしの関係を整理して principle に書いてください。何を経て古いものを手放したか、表と裏がどう食い違い、"
        f"この{subject}の中でどう折り合っているかを、出来事や人との関わりとして書く。食い違うミームも、どちらかを捨てずに両方を生かす。"
        f"ミームの文面をそのまま書き写さない。説明もこの整理と矛盾させない。"
    )


_PERSON_CONTENT_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
新しく生まれる人物1件について、人物説明・年齢・口調などを、自然な日本語で決めてください。
出身地の説明・参考地域・参考文化・参考時代や、所属する地域、この場所・時刻に関連する筋書きに、この人物の生活・仕事・性格が自然に馴染むよう考慮してください(参考地域・参考文化・参考時代は、固有名詞をそのまま持ち込むのではなく、地理・気候・生業・価値観の手がかりとして使ってください)。
「体現する要素」を渡したときは、複数の立場のうちあなたが選びやすいものへ寄せず、渡された要素をこの人物の生き方の核として必ず反映してください。
「既にいる人物・対象」を渡したときは、その役割・関係・特徴とは重ならない人物にしてください(同じ立場・同じ能力・同じ関係性の作り直しをしない)。
{_MATERIAL_INSTRUCTION}
{_LATER_INSTRUCTION}
「性格」は各軸を {'/'.join(PERSONALITY_LEVELS)} の五段階で渡す(サイコロで決まっていて変えられない)。人物説明はこの段階と矛盾しないようにし、「無」「必」の軸はその極端さが生活・仕事・人との関わり方に具体的な癖として表れるように書く。段階の語をそのまま書き写さない。
{_meme_instruction("人物")}
{_PLACEHOLDER_INSTRUCTION}
性別・体格・一人称・二人称・三人称・口調が「決まっている」で null なら、候補から選ぶのではなく、人物像・年齢・出自・生い立ちに合わせてあなた自身で考えて決める。
誰にでも当てはまる無難なものに寄せず、この人物固有の言葉づかいにする。"""

_NON_PERSON_CONTENT_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
ある場所と、そこに居る人物・既にある対象を渡すので、この場所を拠り所に生まれる人物以外の対象(国・組織・商会・氏族・集団など、まとまりとして動くもの。あるいは物)を1件だけ考えてください。
出身地の産業・地形・人間関係のうち少なくとも一つを具体的に使う。
「体現する要素」を渡したときは、渡された要素をこの対象の成り立ちの核として必ず反映してください。
既にある対象と役割が重なるものは作らない。
{_MATERIAL_INSTRUCTION}
{_LATER_INSTRUCTION}
{_meme_instruction("対象")}
{_PLACEHOLDER_INSTRUCTION}"""

_PERSON_NAME_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
内容が決まっている人物1件に、名前と名字を付けます。材料は日本語の見出しを付けた JSON で渡します。
{CHARACTER_NAMING_INSTRUCTION}
人物説明・年齢・体格や口調から連想できる、この人物に似合う名前にしてください。
居場所の参考地域・参考文化・参考時代を名の響きや漢字・カタカナの選び方の手がかりにして、同じ場所の人物として馴染む名にしてください(固有名詞をそのまま持ち込まない)。
名字は、生まれたときに名乗るものを、出身地・身分・家業・参考文化から決める。
作者が付けたい名を渡したときは、この人物に似合うならそれを使い、合わなければ近い響きにする。"""

_NON_PERSON_NAME_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
内容が決まっている人物以外の対象(国・組織・集団・物など)1件に、名前だけを付けます。材料は日本語の見出しを付けた JSON で渡します。
{IDEA_NAMING_INSTRUCTION}
組織の名は場所名か役割名で呼べる形にする。
居場所の参考地域・参考文化・参考時代を名の響きや漢字・カタカナの選び方の手がかりにして、同じ場所のものとして馴染む名にしてください(固有名詞をそのまま持ち込まない)。
既にいる人物・対象の名と紛らわしい名にしない。
作者が付けたい名を渡したときは、この対象に似合うならそれを使い、合わなければ近い響きにする。"""

_POLISH_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
決まったばかりの人物・対象の説明(下書き)と、その下書きに関係する設定を渡すので、設定を踏まえて説明を清書してください。
下書きの人物像・生い立ち・関係・長さは変えない。設定と食い違うところ、設定を踏まえると具体的にできるところだけを直す。
{IDEA_CONTEXT_INSTRUCTION}
{_PLACEHOLDER_INSTRUCTION}"""

_ELEMENT_SYSTEM_PROMPT = """\
あなたは筋書きの構成を分析する設定作家です。
渡す筋書きの本文から、その筋書きの中で人物が生きうる、互いに重ならない具体的な立場・職業・関わり方を抜き出してください。
筋書きが複数の立場を挙げている場合は、それぞれを一つずつの要素にして漏らさず拾ってください。
筋書きに出てくる特定の人物(主人公やその家族・仲間など)が担う役どころそのものは抜き出さないでください。その人物の写しになってしまうため、同じ筋書きの世界で別の人物が就きうる立場として書いてください。
筋書きは時の流れをまたいで書かれている。渡す現在の時刻にまだ始まっていない立場(筋書きの中で後の年に起きる出来事や、「この時刻より後に始まる設定(まだ無い)」を前提にする立場)は抜き出さないでください。"""


def _element(ai: AIClient, rng: random.Random, request: StoryElementsRequestSerialized) -> str | None:
    """抜き出しと選択(`rng.choice`)を分けることで、複数の立場を持つ筋書きでも生成のたびランダムに割り振られるようにし、
    モデルが生成時に自由選択して同じ立場へ偏るのを防ぐ。"""
    if not request.stories:
        return None
    decided = ai.try_generate_json(
        request.model_dump_json(indent=2),
        StoryElementsDraft.model_json_schema(), system=_ELEMENT_SYSTEM_PROMPT)
    try:
        elements = StoryElementsDraft.model_validate(decided).elements
    except ValidationError:
        return None
    return rng.choice(elements) if elements else None


def _nearby_characters(s: Session, born_place_id: int | None, time: Stamp) -> list[Character]:
    """件数は `constants.NEARBY_CHARACTER_LIMIT` まで(祖先をたどるほど無際限に増えるため)。"""
    if born_place_id is None:
        return []
    place_ids = [step.id for step in common_query.place_path(s, born_place_id)]
    ids = s.scalars(common_query.resident_character_ids_select(place_ids, time)).all()[:constants.NEARBY_CHARACTER_LIMIT]
    return list(s.scalars(select(Character).where(Character.id.in_(ids))).all()) if ids else []


def _birth_material(
    s: Session, ai: AIClient, rng: random.Random, born_place_id: int | None, time: Stamp, person: bool,
    parameters: CharacterParameterValues | None, name: str | None, kind: str | None, age: int | None,
    form: CharacterForm | None,
) -> CharacterBirthMaterialSerialized:
    born_place = (s.scalar(
        select(Location).where(Location.id == born_place_id)
        .options(joinedload(Location.parent)).execution_options(populate_existing=True))
        if born_place_id is not None else None)
    stories = story_createion_query.load_location_story(s, born_place_id, time) if born_place_id is not None else []
    later_ideas = (s.scalars(dictionary_query.later_ideas_select(
        common_query.idea_scope_ids(s, born_place_id), time)).all() if born_place_id is not None else [])
    elements_request = StoryElementsRequestSerialized(time=time, stories=stories, later_ideas=later_ideas)
    return CharacterBirthMaterialSerialized(
        time=time,
        person=person,
        born_place=BirthPlaceMaterial.model_validate(born_place) if born_place is not None else None,
        stories=elements_request.stories,
        later_ideas=elements_request.later_ideas,
        element=_element(ai, rng, elements_request),
        memes=draw(s, rng, constants.MEME_PERSON_CATEGORIES if person else constants.MEME_NON_PERSON_CATEGORIES),
        nearby_characters=_nearby_characters(s, born_place_id, time),
        parameters=parameters,
        name=name,
        kind=kind,
        age=age,
        hint_name=form.name if form else None,
        hint_text=form.text if form else None,
    )


def _content(
    ai: AIClient, material: CharacterBirthMaterialSerialized, request: str,
) -> PersonContentDraft | NonPersonContentDraft | None:
    draft_model: type[PersonContentDraft] | type[NonPersonContentDraft] = (
        PersonContentDraft if material.person else NonPersonContentDraft)
    decided = ai.try_generate_json(
        "\n".join([material.model_dump_json(indent=2), request]),
        draft_model.model_json_schema(),
        system=_PERSON_CONTENT_SYSTEM_PROMPT if material.person else _NON_PERSON_CONTENT_SYSTEM_PROMPT)
    try:
        return draft_model.model_validate(decided)
    except ValidationError as error:
        print(f"[data_access_logic/character] 中身が得られなかった: {error}")
        return None


def _polished(s: Session, ai: AIClient, draft: str, born_place_id: int | None, time: Stamp) -> tuple[str, list[IdeaMaterial]]:
    """下書きに関係する設定があれば、それを踏まえて清書する。結ぶアイデアも返す。"""
    ideas = gather_ideas(s, draft, ai, born_place_id, time)
    if not ideas.related:
        return draft, ideas.linked
    decided = ai.try_generate_json(
        "\n".join([PolishRequestSerialized(draft=draft, ideas=ideas).model_dump_json(indent=2),
                   "この説明を清書してください。"]),
        PolishDraft.model_json_schema(), system=_POLISH_SYSTEM_PROMPT, timeout=constants.IDEA_POLISH_TIMEOUT)
    try:
        return PolishDraft.model_validate(decided).text, ideas.linked
    except ValidationError:
        return draft, ideas.linked


def _history(items: list[HistoryItemDraft], born_year: int, age: int) -> str:
    rows = sorted((item for item in items if item.text.strip() and item.age <= age), key=lambda item: item.age)
    return "\n".join(f"- {born_year + item.age}年({item.age}歳): {item.text.strip()}" for item in rows)


def _composed(
    text: str, content: PersonContentDraft | NonPersonContentDraft, memes: list[DrawnMeme], time: Stamp,
    age: int | None,
) -> str:
    if isinstance(content, PersonContentDraft) and age is not None:
        born_year = time.year - age
        text += f"\n\n# 来歴\n{_history(content.history, born_year, age)}"
    if memes:
        text += "\n\n# meme\n" + "\n".join(f"- {drawn.position}: {drawn.text}" for drawn in memes)
        if content.principle:
            text += f"\n\n# 行動原理\n{content.principle}"
    return text


def _name(ai: AIClient, material: CharacterNameMaterialSerialized, person: bool) -> PersonNameDraft | NameDraft | None:
    draft_model: type[PersonNameDraft] | type[NameDraft] = PersonNameDraft if person else NameDraft
    decided = ai.try_generate_json(
        "\n".join([material.model_dump_json(indent=2),
                   "この一件に似合う名前を決めてください。"]),
        draft_model.model_json_schema(),
        system=_PERSON_NAME_SYSTEM_PROMPT if person else _NON_PERSON_NAME_SYSTEM_PROMPT)
    try:
        return draft_model.model_validate(decided)
    except ValidationError:
        return None


def _starting_parameters(rng: random.Random, person: bool, form: CharacterForm | None) -> CharacterParameterValues:
    """性格はサイコロで決め、作者が決めた値はサイコロや AI の決定より優先する。人物以外は名字・体格・口調を持たない。"""
    parameters = rolled(rng)
    if form is not None and form.parameters:
        overlay(parameters, form.parameters[0])
    return parameters if person else without_person_values(parameters)


def generate_character(
    s: Session,
    ai: AIClient,
    rng: random.Random,
    born_place_id: int | None,
    time: Stamp,
    person: bool,
    form: CharacterForm | None = None,
) -> Character | None:
    """`form` は作者の下書き(GUI の欄の値)。名前・説明は核として AI に渡し、性格・種別・生年・没年・
    メインキャラクターかは決まった値として使う。中身が得られなければ足さずに None を返す。"""
    parameters = _starting_parameters(rng, person, form)
    fixed_kind = form.kind if form and form.kind in constants.NON_PERSON_KINDS else None
    fixed_age = max(0, time.year - form.start.year) if form and form.start is not None else None
    material = _birth_material(
        s, ai, rng, born_place_id, time, person, parameters if person else None,
        None, None if person else fixed_kind, fixed_age, form)
    subject = "人物" if person else "対象"
    content = _content(ai, material, f"この場所に自然な{subject}を1件、決めてください。")
    if content is None:
        return None

    if isinstance(content, PersonContentDraft):
        kind = CHARACTER_KIND_PERSON
        parameters.dialect = content.dialect or None
        parameters.sex = parameters.sex or content.sex or None
        parameters.build = parameters.build or content.build or None
        parameters.first_person = parameters.first_person or content.first_person or None
        parameters.second_person = parameters.second_person or content.second_person or None
        parameters.third_person = parameters.third_person or content.third_person or None
        parameters.tone = parameters.tone or content.tone or None
    else:
        kind = fixed_kind or (content.kind if content.kind in constants.NON_PERSON_KINDS
                              else rng.choice(constants.NON_PERSON_KINDS))
    age = fixed_age if fixed_age is not None else content.age
    text, ideas = _polished(s, ai, content.text, born_place_id, time)
    text = _composed(text, content, material.memes, time, age)

    named = _name(ai, CharacterNameMaterialSerialized(
        kind=kind, text=text, age=age, parameters=parameters if person else None,
        born_place=material.born_place, nearby_characters=material.nearby_characters,
        hint_name=form.name if form else None,
    ), person)
    name = named.name if named is not None else (form.name if form and form.name else subject)
    if isinstance(named, PersonNameDraft):
        parameters.family_name = named.family_name or None

    birth = Stamp(time.year - age)
    record = Character(
        name=name,
        kind=kind,
        text=fill_name_placeholder(text, name),
        main_character=bool(form.main_character) if form and form.main_character is not None else False,
        confirmed=ConfirmStatus.PENDING,
        # 生まれた時点で決める値なので、期間を限らない一行だけを持つ。死亡していなければ end は空
        parameters=[parameter_row(parameters, birth, form.end if form else None)],
    )
    s.add(record)
    s.flush()
    if born_place_id is not None:
        s.add(CharacterPlace(character_id=record.id, location_id=born_place_id, start=record.start, end=record.end))
    link(s, record, ideas)
    s.commit()

    place_label = (f"{material.born_place.name}(id={material.born_place.id})" if material.born_place else "不明")
    print(f"[data_access_logic/character] {time} 生成: {record.name} id={record.id} 種別={record.kind}"
          f" 出自={place_label} 年齢={age}\n"
          f"    筋書きの要素: {material.element or '(無し)'}\n"
          + "".join(f"    ミーム: {drawn.position}: {drawn.text}\n" for drawn in material.memes)
          + f"    説明: {record.text}")
    return record


def complete_text(s: Session, ai: AIClient, rng: random.Random, character_id: int) -> Character:
    """人物・対象の本文(text)が空のとき、決まっている名前・属性・出自を核に AI に本文だけを書かせて埋める。
    性別・体格・口調・性格・種別・生年・没年・名前は変えない。"""
    record = s.get_one(Character, character_id)
    if (record.text or "").strip():
        raise ValueError("text はすでに埋まっている")
    time = s.scalar(common_query.latest_time_select()) or record.start
    if time is None:
        raise ValueError("time が決められない(世界にまだ出来事が無く、record.start も空)")
    person = record.kind == CHARACTER_KIND_PERSON
    # places は新しい順なので、末尾が生まれた場所
    born_place_id = record.places[-1].location_id if record.places else None
    age = max(0, time.year - record.start.year) if record.start is not None else None
    parameters = parameters_at(record, time) if person else None
    name = record.name
    material = _birth_material(
        s, ai, rng, born_place_id, time, person, parameters, name, None if person else record.kind, age, None)
    subject = "人物" if person else "対象"
    content = _content(ai, material, f"この{subject}の本文(説明)を決めてください。")
    if content is None:
        raise ValueError("本文が得られなかった")

    text, ideas = _polished(s, ai, content.text, born_place_id, time)
    text = _composed(text, content, material.memes, time, age)
    record = s.get_one(Character, character_id)
    record.text = fill_name_placeholder(text, name or "")
    link(s, record, ideas)
    s.commit()
    return record

