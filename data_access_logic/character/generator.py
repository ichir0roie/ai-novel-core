#!/usr/bin/env python3
"""人物・人物以外の対象(国・組織・集団・物)を一件生む。中身(説明・年齢・口調)→ 設定を踏まえた清書 → 名付け、の順に AI に決めさせる。

名前は中身が決まったあとに、その内容から連想して決める。生んだ人物は `confirmed=未確認` で足す。

db だけの段(`birth_sources` → 語をアイデアと照らす `resolve_ideas` → `save_character`)と、AI・乱数だけの段
(`character_content` → `character_creation`)に分けてある。手元では `generate_character` がつなぎ、
web のセッションでは `web_session/character.py` が API 越しにつなぐ。
"""
from __future__ import annotations

import logging
import random

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
    BirthLocationMaterial, BirthSources, CharacterBirthMaterialSerialized, CharacterContent, CharacterCreation,
    CharacterNameMaterialSerialized, CompletionTarget, HistoryItemDraft, NameDraft, NearbyCharacter, NonPersonContentDraft,
    PersonContentDraft, PersonNameDraft, PolishDraft, PolishRequestSerialized, ScenePersonContentDraft,
    StoryElementsDraft, StoryElementsRequestSerialized,
)
from data_access_logic.character.histories import histories_at
from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.character.parameters import overlay, parameter_row, parameters_at, rolled, without_person_values
from data_access_logic.character.record import CharacterHistoryRow
from data_access_logic.idea.context import resolve_ideas
from data_access_logic.idea.links import link
from data_access_logic.idea.models import IdeaContextMaterial, IdeaMaterial
from data_access_logic.idea.search import keywords_of
from data_access_logic.meme.extractor import draw_from, meme_pool, position_legend
from data_access_logic.meme.models import DrawnMeme
from data_access_logic.query import common_query, dictionary_query, story_creation_query
from data_access_logic.story.models import StoryPlotMaterial
from db.child_lists import replaced_rows
from db.schema import (
    CHARACTER_KIND_PERSON, PERSONALITY_LEVELS, Character, CharacterHistory, CharacterLocation, ConfirmStatus, Location,
)
from db.stamp import Stamp

logger = logging.getLogger(__name__)

_PLACEHOLDER_INSTRUCTION = (
    f"この一件の名前はまだ決まっていない。説明の中でこの一件を指すときは必ず「{NAME_PLACEHOLDER}」と書き、名前を考案して書き込まない。"
)

_LATER_INSTRUCTION = (
    "筋書きや既にいる人物・対象の説明は、現在の時刻より後の姿で書かれていることがある。"
    "「この時刻より後に始まる設定(まだ無い)」を渡したときは、それはまだ世に無い。その設定に当たる立場・仕事・組織・技術・出来事を、"
    "来歴にも現在の姿にも出さず、既にいる人物の説明に出てきても、この時刻にはまだ無いものとして扱う。"
)

# 生んだ一件はこの時刻から先の出来事・話で使われるので、先の姿を決めておくと、後で生む出来事・話と食い違う
_PRESENT_INSTRUCTION = (
    "説明・来歴・行動原理には、現在の時刻までのことだけを書く。現在の時刻より後に起きること(後年の立場・仕事・住まい・人間関係・"
    "行く末・死)は書かず、「のちに」「やがて」のように先を示すこともしない。"
)

_SCENE_INSTRUCTION = (
    "「登場する話のプロット」を渡したときは、この人物はその話に、現在の時刻・出身の場所で、作者の指定の役どころとして登場する。"
    "年齢・立場・仕事・人間関係は、その話でその役を果たせるものにする(上役なら下の者を束ねられる歳と経歴、子どもの遊び仲間なら同じ年頃など)。"
    "プロットに無い出来事を、この人物の来歴に書き足さない。"
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
{_PRESENT_INSTRUCTION}
{_SCENE_INSTRUCTION}
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
{_PRESENT_INSTRUCTION}
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
{_PRESENT_INSTRUCTION}
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
    decided = ai.generate(request.model_dump_json(indent=2), StoryElementsDraft, system=_ELEMENT_SYSTEM_PROMPT)
    if decided is None or not decided.elements:
        return None
    return rng.choice(decided.elements)


def _nearby_characters(s: Session, born_location_id: int | None, time: Stamp) -> list[Character]:
    """件数は `constants.NEARBY_CHARACTER_LIMIT` まで(祖先をたどるほど無際限に増えるため)。"""
    if born_location_id is None:
        return []
    location_ids = [step.id for step in common_query.location_path(s, born_location_id)]
    ids = s.scalars(common_query.resident_character_ids_select(location_ids, time)).all()[:constants.NEARBY_CHARACTER_LIMIT]
    return list(s.scalars(select(Character).where(Character.id.in_(ids))).all()) if ids else []


def _meme_categories(person: bool) -> tuple[str, ...]:
    return constants.MEME_PERSON_CATEGORIES if person else constants.MEME_NON_PERSON_CATEGORIES


def birth_sources(s: Session, born_location_id: int | None, time: Stamp, person: bool) -> BirthSources:
    born_location = (s.scalar(
        select(Location).where(Location.id == born_location_id)
        .options(joinedload(Location.parent)).execution_options(populate_existing=True))
        if born_location_id is not None else None)
    stories = story_creation_query.load_location_story(s, born_location_id, time) if born_location_id is not None else []
    later_ideas = (s.scalars(dictionary_query.later_ideas_select(
        common_query.idea_scope_ids(s, born_location_id), time)).all() if born_location_id is not None else [])
    return BirthSources(
        born_location=BirthLocationMaterial.model_validate(born_location) if born_location is not None else None,
        stories=[StoryPlotMaterial.model_validate(story) for story in stories],
        later_ideas=[IdeaMaterial.model_validate(idea) for idea in later_ideas],
        nearby_characters=[NearbyCharacter(name=character.name, kind=character.kind,
                                           histories=histories_at(character, time))
                           for character in _nearby_characters(s, born_location_id, time)],
        meme_pool=meme_pool(s, _meme_categories(person)),
    )


def _hint_text(form: CharacterForm | None) -> str | None:
    if form is None:
        return None
    return "\n\n".join(history.description for history in form.histories) or None


def _birth_material(
    ai: AIClient, rng: random.Random, sources: BirthSources, time: Stamp, person: bool,
    parameters: CharacterParameterValues | None, name: str | None, kind: str | None, age: int | None,
    form: CharacterForm | None, plot_text: str | None = None,
) -> CharacterBirthMaterialSerialized:
    elements_request = StoryElementsRequestSerialized(time=time, stories=sources.stories, later_ideas=sources.later_ideas)
    return CharacterBirthMaterialSerialized(
        time=time,
        person=person,
        born_location=sources.born_location,
        stories=elements_request.stories,
        later_ideas=elements_request.later_ideas,
        element=_element(ai, rng, elements_request),
        memes=draw_from(rng, sources.meme_pool, _meme_categories(person)),
        nearby_characters=sources.nearby_characters,
        parameters=parameters,
        name=name,
        kind=kind,
        age=age,
        hint_name=form.name if form else None,
        hint_text=_hint_text(form),
        plot_text=plot_text,
    )


def _content(
    ai: AIClient, material: CharacterBirthMaterialSerialized, request: str,
) -> PersonContentDraft | NonPersonContentDraft | None:
    draft_model: type[PersonContentDraft] | type[NonPersonContentDraft] = (
        NonPersonContentDraft if not material.person
        else ScenePersonContentDraft if material.plot_text else PersonContentDraft)
    decided = ai.generate(
        "\n".join([material.model_dump_json(indent=2), request]),
        draft_model,
        system=_PERSON_CONTENT_SYSTEM_PROMPT if material.person else _NON_PERSON_CONTENT_SYSTEM_PROMPT)
    if decided is None:
        logger.warning("中身が得られなかった")
    return decided


def _polished(ai: AIClient, draft: str, ideas: IdeaContextMaterial) -> str:
    """下書きに関係する設定があれば、それを踏まえて清書する。"""
    if not ideas.related:
        return draft
    decided = ai.generate(
        "\n".join([PolishRequestSerialized(draft=draft, ideas=ideas).model_dump_json(indent=2),
                   "この説明を清書してください。"]),
        PolishDraft, system=_POLISH_SYSTEM_PROMPT, timeout=constants.IDEA_POLISH_TIMEOUT)
    return draft if decided is None else decided.text


def _history(items: list[HistoryItemDraft], born_year: int, age: int) -> list[CharacterHistoryRow]:
    rows = sorted((item for item in items if item.text.strip() and item.age <= age), key=lambda item: item.age)
    return [CharacterHistoryRow(start=Stamp(born_year + item.age), description=item.text.strip()) for item in rows]


def _histories(
    text: str, content: PersonContentDraft | NonPersonContentDraft, memes: list[DrawnMeme], time: Stamp,
    age: int | None, name: str,
) -> list[CharacterHistoryRow]:
    """芯(説明・meme・行動原理)は始まりの無い一行に、来歴の節目は、その年から始まる行に一件ずつ置く。"""
    if memes:
        text += "\n\n# meme\n" + "\n".join(f"- {drawn.position}: {drawn.text}" for drawn in memes)
        if content.principle:
            text += f"\n\n# 行動原理\n{content.principle}"
    rows = [CharacterHistoryRow(description=text)]
    if isinstance(content, PersonContentDraft) and age is not None:
        rows += _history(content.history, time.year - age, age)
    for row in rows:
        row.description = fill_name_placeholder(row.description, name)
    return rows


def _name(ai: AIClient, material: CharacterNameMaterialSerialized, person: bool) -> PersonNameDraft | NameDraft | None:
    draft_model: type[PersonNameDraft] | type[NameDraft] = PersonNameDraft if person else NameDraft
    return ai.generate(
        "\n".join([material.model_dump_json(indent=2),
                   "この一件に似合う名前を決めてください。"]),
        draft_model,
        system=_PERSON_NAME_SYSTEM_PROMPT if person else _NON_PERSON_NAME_SYSTEM_PROMPT)


def _starting_parameters(rng: random.Random, person: bool, form: CharacterForm | None) -> CharacterParameterValues:
    """性格はサイコロで決め、作者が決めた値はサイコロや AI の決定より優先する。人物以外は名字・体格・口調を持たない。"""
    parameters = rolled(rng)
    if form is not None and form.parameters:
        overlay(parameters, form.parameters[0])
    return parameters if person else without_person_values(parameters)


def character_content(
    ai: AIClient, rng: random.Random, sources: BirthSources, time: Stamp, person: bool, form: CharacterForm | None,
    plot_text: str | None = None,
) -> CharacterContent | None:
    """`form` は作者の下書き(GUI の欄の値)。名前・説明は核として AI に渡し、性格・種別・生年は決まった値として使う。
    `plot_text` はこの人物を登場させる話のプロット。生年が決まっていなければ、その役どころに合う年齢を AI に決めさせる。
    中身が得られなければ None。"""
    parameters = _starting_parameters(rng, person, form)
    fixed_kind = form.kind if form and form.kind in constants.NON_PERSON_KINDS else None
    fixed_age = max(0, time.year - form.start.year) if form and form.start is not None else None
    material = _birth_material(
        ai, rng, sources, time, person, parameters if person else None,
        None, None if person else fixed_kind, fixed_age, form, plot_text)
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
    return CharacterContent(
        material=material, content=content, kind=kind, age=fixed_age if fixed_age is not None else content.age,
        parameters=parameters)


def character_creation(
    ai: AIClient, decided: CharacterContent, ideas: IdeaContextMaterial, born_location_id: int | None,
    form: CharacterForm | None,
) -> CharacterCreation:
    """`ideas` は中身の説明(`decided.content.text`)の語をアイデアと照らしたもの。清書して名付ける。"""
    material = decided.material
    person = material.person
    parameters = decided.parameters
    text = _polished(ai, decided.content.text, ideas)
    named = _name(ai, CharacterNameMaterialSerialized(
        kind=decided.kind, text=text, age=decided.age, parameters=parameters if person else None,
        born_location=material.born_location, nearby_characters=material.nearby_characters,
        hint_name=form.name if form else None,
    ), person)
    subject = "人物" if person else "対象"
    name = named.name if named is not None else (form.name if form and form.name else subject)
    if isinstance(named, PersonNameDraft):
        parameters.family_name = named.family_name or None

    location_label = (f"{material.born_location.name}(id={material.born_location.id})" if material.born_location else "不明")
    logger.info(f"{material.time} 生成: {name} 種別={decided.kind} 出自={location_label} 年齢={decided.age}\n"
                f"    筋書きの要素: {material.element or '(無し)'}\n"
                + "".join(f"    ミーム: {drawn.position}: {drawn.text}\n" for drawn in material.memes))
    return CharacterCreation(
        name=name,
        kind=decided.kind,
        histories=_histories(text, decided.content, material.memes, material.time, decided.age, name),
        main_character=bool(form.main_character) if form and form.main_character is not None else False,
        parameters=parameters,
        birth=Stamp(material.time.year - decided.age),
        # 死は先の出来事なので、作者が主要人物に決めて渡したときだけ持たせる(サブキャラクターには持たせない)
        end=form.end if form and form.main_character else None,
        born_location_id=born_location_id,
        ideas=ideas.linked,
    )


def save_character(s: Session, creation: CharacterCreation) -> Character:
    record = Character(
        name=creation.name,
        kind=creation.kind,
        main_character=creation.main_character,
        confirmed=ConfirmStatus.PENDING,
        end=creation.end,
        # 生まれた時点で決める値なので、誕生から効く一行だけを持つ
        parameters=[parameter_row(creation.parameters, creation.birth)],
        histories=replaced_rows([], creation.histories, CharacterHistory),
    )
    s.add(record)
    s.flush()
    if creation.born_location_id is not None:
        s.add(CharacterLocation(character_id=record.id, location_id=creation.born_location_id,
                                start=record.start, end=record.end))
    link(s, record, creation.ideas)
    logger.info(f"足した: {record.name} id={record.id}")
    return record


def generate_character(
    s: Session,
    ai: AIClient,
    rng: random.Random,
    born_location_id: int | None,
    time: Stamp,
    person: bool,
    form: CharacterForm | None = None,
    plot_text: str | None = None,
) -> Character | None:
    """中身が得られなければ足さずに None を返す。`plot_text` は登場させる話のプロット(`character_content`)。"""
    decided = character_content(
        ai, rng, birth_sources(s, born_location_id, time, person), time, person, form, plot_text)
    if decided is None:
        return None
    ideas = resolve_ideas(s, keywords_of(decided.content.text, ai, time), born_location_id, time)
    # AI が洗い出した語から足した候補は、この後の生成が失敗しても残す
    s.commit()
    record = save_character(s, character_creation(ai, decided, ideas, born_location_id, form))
    s.commit()
    return record


def completion_target(s: Session, character_id: int) -> CompletionTarget:
    record = s.get_one(Character, character_id)
    if record.histories:
        raise ValueError("histories(説明・来歴)はすでにある")
    time = s.scalar(common_query.latest_time_select()) or record.start
    if time is None:
        raise ValueError("time が決められない(世界にまだ出来事が無く、record.start も空)")
    person = record.kind == CHARACTER_KIND_PERSON
    return CompletionTarget(
        id=record.id, name=record.name, kind=record.kind, time=time, person=person,
        # locations は新しい順なので、末尾が生まれた場所
        born_location_id=record.locations[-1].location_id if record.locations else None,
        age=max(0, time.year - record.start.year) if record.start is not None else None,
        parameters=parameters_at(record, time) if person else None,
    )


def completion_content(
    ai: AIClient, rng: random.Random, target: CompletionTarget, sources: BirthSources,
) -> tuple[CharacterBirthMaterialSerialized, PersonContentDraft | NonPersonContentDraft]:
    """決まっている名前・属性・出自を核に、説明・来歴だけを AI に書かせる。"""
    material = _birth_material(
        ai, rng, sources, target.time, target.person, target.parameters, target.name,
        None if target.person else target.kind, target.age, None)
    subject = "人物" if target.person else "対象"
    content = _content(ai, material, f"この{subject}の説明を決めてください。")
    if content is None:
        raise ValueError("説明が得られなかった")
    return material, content


def completed_histories(
    ai: AIClient, target: CompletionTarget, material: CharacterBirthMaterialSerialized,
    content: PersonContentDraft | NonPersonContentDraft, ideas: IdeaContextMaterial,
) -> list[CharacterHistoryRow]:
    return _histories(_polished(ai, content.text, ideas), content, material.memes, target.time, target.age,
                      target.name or "")


def save_completed_histories(
    s: Session, character_id: int, histories: list[CharacterHistoryRow], ideas: list[IdeaMaterial],
) -> Character:
    record = s.get_one(Character, character_id)
    record.histories = replaced_rows([], histories, CharacterHistory)
    link(s, record, ideas)
    s.flush()
    return record


def complete_histories(s: Session, ai: AIClient, rng: random.Random, character_id: int) -> Character:
    """人物・対象の説明・来歴(histories)が一行も無いとき、決まっている名前・属性・出自を核に AI に説明・来歴だけを書かせて埋める。
    性別・体格・口調・性格・種別・生年・没年・名前は変えない。"""
    target = completion_target(s, character_id)
    material, content = completion_content(
        ai, rng, target, birth_sources(s, target.born_location_id, target.time, target.person))
    ideas = resolve_ideas(s, keywords_of(content.text, ai, target.time), target.born_location_id, target.time)
    s.commit()
    record = save_completed_histories(
        s, character_id, completed_histories(ai, target, material, content, ideas), ideas.linked)
    s.commit()
    return record
