#!/usr/bin/env python3
"""人物・人物以外の対象(国・組織・集団・物)を一件生む。中身(説明・年齢・口調)→ 関係する設定と世界との食い違いの検め
(`consistency.py`)→ 名付け(`naming.py`)、の順に AI に決めさせる。

名前は中身が決まったあとに、その内容と居場所から候補を出させ、同じ場所にいる人物・対象の名を避けてサイコロで選ぶ。

db だけの段(`birth_sources` → 語をアイデアと照らす `resolve_ideas` → `save_character`)と、AI・乱数だけの段
(`character_content` → `character_creation`)に分けてある。流れ(`data_access_logic/flows/character.py`)がつなぐ。
"""
from __future__ import annotations

import logging
import random
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ai.instructions.naming import NAME_PLACEHOLDER, fill_name_placeholder
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.character.form import CharacterForm
from data_access_logic.character.generator_models import (
    BirthLocationMaterial, BirthSources, CharacterBirthMaterialSerialized, CharacterContent, CharacterCreation,
    CharacterNameMaterialSerialized, CharacterWriting, CompletionTarget, HistoryItemDraft, NearbyCharacter, NonPersonContentDraft,
    PersonContentDraft, PersonNameDraft, StoryElementsDraft, StoryElementsRequestSerialized,
)
from data_access_logic.character.histories import add_history, histories_at
from data_access_logic.character.consistency import Reconciled, reconciled
from data_access_logic.character.models import CharacterParameterValues
from data_access_logic.character.naming import named
from data_access_logic.character.parameters import overlay, parameter_row, parameters_at, rolled, without_person_values
from data_access_logic.character.record import CharacterHistoryRow
from data_access_logic.idea.models import IdeaContextMaterial, IdeaMaterial
from data_access_logic.meme.extractor import draw_from, meme_pool, position_legend
from data_access_logic.meme.models import DrawnMeme
from data_access_logic.query import common_query, dictionary_query, story_creation_query
from data_access_logic.story.models import StoryPlotMaterial
from db.child_lists import replaced_histories
from db.schema import (
    CHARACTER_KIND_PERSON, PERSONALITY_LEVELS, Character, CharacterHistory, CharacterLocation, Location,
)
from db.stamp import Stamp

logger = logging.getLogger(__name__)

# 名前は後で機械的に入れる(`fill_name_placeholder`)ので、決まっている名前・作者の指定の名があっても仮置きで書かせる
_PLACEHOLDER_INSTRUCTION = (
    f"説明の中でこの一件を指すときは、名前を書かず必ず「{NAME_PLACEHOLDER}」と書く(名前はあとで入れる)。名前を考案して書き込まない。"
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

# 生成した場所は、その一件の居場所として出自から今まで続く行で足すので、今の暮らしもそこに置かせる
_PLACE_INSTRUCTION = (
    "この一件は「出身」の場所で生まれ(成り立ち)、現在の時刻もそこ(かその中の場所)で暮らし・働いている(拠点を置いている)。"
    "説明・来歴の現在の住まい・仕事場・拠点は、出身の場所かその中に置く。筋書きや体現する要素が別の場所での役どころを示していても、"
    "出身の場所でその役を担う形に移すか、出身の場所から通う・関わる形にする。一時よそへ出た来歴はよいが、現在は出身の場所にいるようにする。"
)

_SCENE_INSTRUCTION = (
    "「登場する話のプロット」を渡したときは、この一件はその話に、現在の時刻・出身の場所で、作者の指定の役どころとして登場する。"
    "年齢・立場・仕事・人間関係は、その話でその役を果たせるものにする(上役なら下の者を束ねられる歳と経歴、子どもの遊び仲間なら同じ年頃など)。"
    "来歴には、プロットの筋と食い違う出来事や、プロットでこれから起きる出来事を書かない。"
)

_MATERIAL_INSTRUCTION = """\
材料は日本語の見出しを付けた JSON で渡す。
「決まっている」の値が null でなければ、その値をそのまま使う。
「作者の指定」と「登場する話のプロット」の役どころは核にする。足りないところを補い、言い回しは変えてよい。
「体現する要素」は、作者の指定もプロットも無いときだけ渡す。渡したときは、それをこの一件の生き方・成り立ちの核として必ず反映する。
「既にいる人物・対象」とは、役割・関係・特徴が重ならないようにする(同じ立場・同じ能力・同じ関係性の作り直しをしない)。ただし作者の指定・プロットの役どころが求める立場はそのまま使う。"""


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
{_MATERIAL_INSTRUCTION}
{_LATER_INSTRUCTION}
{_PRESENT_INSTRUCTION}
{_PLACE_INSTRUCTION}
{_SCENE_INSTRUCTION}
「性格」は各軸を {'/'.join(PERSONALITY_LEVELS)} の五段階で渡す(サイコロか作者の指定で決まっていて変えられない)。人物説明はこの段階と矛盾しないようにし、「無」「必」の軸はその極端さが生活・仕事・人との関わり方に具体的な癖として表れるように書く。段階の語をそのまま書き写さない。
{_meme_instruction("人物")}
{_PLACEHOLDER_INSTRUCTION}
性別・体格・一人称・二人称・三人称・口調・方言が「決まっている」で null なら、人物像・年齢・出自・生い立ちに合わせてあなた自身で考えて決める(null でなければ、その値をそのまま返す)。
誰にでも当てはまる無難なものに寄せず、この人物固有の言葉づかいにする。"""

_NON_PERSON_CONTENT_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
ある場所と、そこに居る人物・既にある対象を渡すので、この場所を拠り所に生まれる人物以外の対象(国・組織・商会・氏族・集団など、まとまりとして動くもの。あるいは物)を1件だけ考えてください。
出身地の説明・環境・人間関係のうち少なくとも一つを具体的に使う。
{_MATERIAL_INSTRUCTION}
{_LATER_INSTRUCTION}
{_PRESENT_INSTRUCTION}
{_PLACE_INSTRUCTION}
{_SCENE_INSTRUCTION}
{_meme_instruction("対象")}
{_PLACEHOLDER_INSTRUCTION}"""

_ELEMENT_SYSTEM_PROMPT = """\
あなたは筋書きの構成を分析する設定作家です。
渡す筋書きの本文から、その筋書きの中で人物が生きうる、互いに重ならない具体的な立場・職業・関わり方を抜き出してください。
筋書きが複数の立場を挙げている場合は、それぞれを一つずつの要素にして漏らさず拾ってください。
筋書きに出てくる特定の人物(主人公やその家族・仲間など)が担う役どころそのものは抜き出さないでください。その人物の写しになってしまうため、同じ筋書きの世界で別の人物が就きうる立場として書いてください。
筋書きは時の流れをまたいで書かれている。渡す現在の時刻にまだ始まっていない立場(筋書きの中で後の年に起きる出来事や、「この時刻より後に始まる設定(まだ無い)」を前提にする立場)は抜き出さないでください。"""


def story_elements(ai: AIClient, sources: BirthSources, time: Stamp) -> list[str]:
    """筋書きから人物が生きうる立場を抜き出す。抜き出しと選択(`rng.choice`)を分けることで、複数の立場を持つ筋書きでも
    生成のたびランダムに割り振られるようにし、モデルが生成時に自由選択して同じ立場へ偏るのを防ぐ。
    同じ場所・時刻に何人か生むときは、一度だけ抜き出して使い回す(`GenerateCharacters`)。"""
    if not sources.stories:
        return []
    request = StoryElementsRequestSerialized(time=time, stories=sources.stories, later_ideas=sources.later_ideas)
    decided = ai.generate(request.model_dump_json(indent=2), StoryElementsDraft, system=_ELEMENT_SYSTEM_PROMPT)
    return [] if decided is None else decided.elements


def _nearby_characters(s: Session, born_location_id: int | None, time: Stamp) -> list[Character]:
    """件数は `constants.NEARBY_CHARACTER_LIMIT` まで(祖先をたどるほど無際限に増えるため)。"""
    if born_location_id is None:
        return []
    location_ids = [step.id for step in common_query.location_path(s, born_location_id)]
    ids = s.scalars(common_query.resident_character_ids_select(location_ids, time)
                    .limit(constants.NEARBY_CHARACTER_LIMIT)).all()
    return list(s.scalars(select(Character).where(Character.id.in_(ids))).all()) if ids else []


def _resident_names(s: Session, born_location_id: int | None, time: Stamp) -> list[str]:
    """居場所とその上位・配下にいる人物・対象の名。同じ回に作ったばかりの人物も入る。"""
    if born_location_id is None:
        return []
    location_ids = {step.id for step in common_query.location_path(s, born_location_id)}
    location_ids.update(common_query.descendant_location_ids(s, born_location_id))
    return list(s.scalars(common_query.resident_names_select(location_ids, time)).all())


def _meme_categories(person: bool) -> tuple[str, ...]:
    return constants.MEME_PERSON_CATEGORIES if person else constants.MEME_NON_PERSON_CATEGORIES


def birth_sources(s: Session, born_location_id: int | None, time: Stamp, person: bool) -> BirthSources:
    born_location = (s.scalar(
        select(Location).where(Location.id == born_location_id)
        .options(joinedload(Location.parent)).execution_options(populate_existing=True))
        if born_location_id is not None else None)
    stories = story_creation_query.load_location_story(s, born_location_id) if born_location_id is not None else []
    later_ideas = (s.scalars(dictionary_query.later_ideas_select(
        common_query.idea_scope_ids(s, born_location_id), time)).all() if born_location_id is not None else [])
    return BirthSources(
        born_location=BirthLocationMaterial.model_validate(born_location) if born_location is not None else None,
        stories=[StoryPlotMaterial.model_validate(story) for story in stories],
        later_ideas=[IdeaMaterial.model_validate(idea) for idea in later_ideas],
        nearby_characters=[NearbyCharacter(name=character.name, kind=character.kind, text=character.text,
                                           histories=histories_at(character, time))
                           for character in _nearby_characters(s, born_location_id, time)],
        resident_names=_resident_names(s, born_location_id, time),
        meme_pool=meme_pool(s, _meme_categories(person)),
    )


def _hint_text(form: CharacterForm | None) -> str | None:
    if form is None:
        return None
    texts = [form.text or "", *(history.description for history in form.histories)]
    return "\n\n".join(text for text in texts if text.strip()) or None


def _birth_material(
    ai: AIClient, rng: random.Random, sources: BirthSources, time: Stamp, person: bool,
    parameters: CharacterParameterValues | None, name: str | None, kind: str | None, age: int | None,
    hint_name: str | None, hint_text: str | None, plot_text: str | None, elements: list[str] | None, draw_memes: bool,
) -> CharacterBirthMaterialSerialized:
    """`elements` を省けば、要るときにその場で筋書きから抜き出す。作者の指定かプロットがあれば、要素は使わない。"""
    element = None
    if not hint_text and not plot_text:
        candidates = story_elements(ai, sources, time) if elements is None else elements
        element = rng.choice(candidates) if candidates else None
    return CharacterBirthMaterialSerialized(
        time=time,
        person=person,
        born_location=sources.born_location,
        stories=sources.stories,
        later_ideas=sources.later_ideas,
        element=element,
        memes=draw_from(rng, sources.meme_pool, _meme_categories(person)) if draw_memes else [],
        nearby_characters=sources.nearby_characters,
        resident_names=sources.resident_names,
        parameters=parameters,
        name=name,
        kind=kind,
        age=age,
        hint_name=hint_name,
        hint_text=hint_text,
        plot_text=plot_text,
    )


def _content(
    ai: AIClient, material: CharacterBirthMaterialSerialized, request: str,
) -> PersonContentDraft | NonPersonContentDraft | None:
    draft_model: type[PersonContentDraft] | type[NonPersonContentDraft] = (
        PersonContentDraft if material.person else NonPersonContentDraft)
    decided = ai.generate(
        "\n".join([material.model_dump_json(indent=2), request]),
        draft_model,
        system=_PERSON_CONTENT_SYSTEM_PROMPT if material.person else _NON_PERSON_CONTENT_SYSTEM_PROMPT)
    if decided is None:
        logger.warning("中身が得られなかった")
    return decided


def _history(items: Sequence[HistoryItemDraft], born_year: int, age: int) -> list[CharacterHistoryRow]:
    """同じ歳の節目は一行にまとめる。"""
    by_year: dict[int, list[str]] = {}
    for item in sorted(items, key=lambda item: item.age):
        if item.text.strip() and item.age <= age:
            by_year.setdefault(born_year + item.age, []).append(item.text.strip())
    # AI の書いた節目には秘密が混じりうるので、関係のある人物に広めず本人だけが知る行にする(作者が公開に直す)
    return [CharacterHistoryRow(start=year, description="\n".join(texts), private=True) for year, texts in by_year.items()]


def _writing(fixed: Reconciled, memes: list[DrawnMeme], time: Stamp, age: int, name: str | None) -> CharacterWriting:
    """芯は `text` に、ミームと行動原理はそれぞれの列に、来歴の節目は、その年から始まる行に置く。
    行動原理はミームどうしの関係なので、ミームが無ければ書かない。
    名前の無い一件(名前の空いた人物の芯を埋めるとき)は、仮置きを残して作者に名を決めてもらう(空文字で消すと文が欠ける)。"""
    def filled(text: str) -> str:
        return fill_name_placeholder(text, name) if name else text

    meme = "\n".join(f"- {drawn.position}: {drawn.text}" for drawn in memes) or None
    principle = filled(fixed.principle) if memes and fixed.principle else None
    rows = _history(fixed.history, time.year - age, age)
    for row in rows:
        row.description = filled(row.description)
    return CharacterWriting(text=filled(fixed.text), meme=meme, principle=principle, histories=rows)


def _starting_parameters(rng: random.Random, person: bool, form: CharacterForm | None) -> CharacterParameterValues:
    """性格はサイコロで決め、作者が決めた値はサイコロや AI の決定より優先する。人物以外は名字・体格・口調を持たない。"""
    parameters = rolled(rng)
    if form is not None and form.parameters:
        overlay(parameters, form.parameters[0])
    return parameters if person else without_person_values(parameters)


def _person_age(content: PersonContentDraft, plot_text: str | None) -> int:
    low, high = constants.SCENE_CHARACTER_AGE_RANGE if plot_text else constants.GENERATION_CHARACTER_AGE_RANGE
    return min(max(content.age, low), high)


def character_content(
    ai: AIClient, rng: random.Random, sources: BirthSources, time: Stamp, person: bool, form: CharacterForm | None,
    plot_text: str | None = None, elements: list[str] | None = None,
) -> CharacterContent | None:
    """`form` は作者の下書き(GUI の欄の値)。名前・説明は核として AI に渡し、性格・口調・種別・生年は決まった値として使う。
    `plot_text` はこの人物を登場させる話のプロット。生年が決まっていなければ、その役どころに合う年齢を AI に決めさせる。
    `elements` は筋書きから抜き出した立場(`story_elements`。省けば要るときに抜き出す)。中身が得られなければ None。"""
    parameters = _starting_parameters(rng, person, form)
    fixed_kind = form.kind if form and form.kind and form.kind != CHARACTER_KIND_PERSON else None
    fixed_age = max(0, time.year - form.start.year) if form and form.start is not None else None
    material = _birth_material(
        ai, rng, sources, time, person, parameters if person else None,
        None, None if person else fixed_kind, fixed_age, form.name if form else None, _hint_text(form), plot_text,
        elements, draw_memes=True)
    subject = "人物" if person else "対象"
    content = _content(ai, material, f"この場所に自然な{subject}を1件、決めてください。")
    if content is None:
        return None

    if isinstance(content, PersonContentDraft):
        kind = CHARACTER_KIND_PERSON
        age = _person_age(content, plot_text)
        parameters.dialect = parameters.dialect or content.dialect or None
        parameters.sex = parameters.sex or content.sex or None
        parameters.build = parameters.build or content.build or None
        parameters.first_person = parameters.first_person or content.first_person or None
        parameters.second_person = parameters.second_person or content.second_person or None
        parameters.third_person = parameters.third_person or content.third_person or None
        parameters.tone = parameters.tone or content.tone or None
    else:
        age = content.age
        kind = fixed_kind or (content.kind if content.kind in constants.NON_PERSON_KINDS
                              else rng.choice(constants.NON_PERSON_KINDS))
    return CharacterContent(
        material=material, content=content, kind=kind, age=fixed_age if fixed_age is not None else age,
        parameters=parameters)


def character_creation(
    ai: AIClient, rng: random.Random, decided: CharacterContent, ideas: IdeaContextMaterial, born_location_id: int | None,
    form: CharacterForm | None,
) -> CharacterCreation:
    """`ideas` は中身の説明(`decided.content.text`)の語をアイデアと照らしたもの。設定・世界と検めて名付ける。"""
    material = decided.material
    person = material.person
    parameters = decided.parameters
    fixed = reconciled(ai, material, decided.kind, decided.age, decided.content, ideas)
    draft = named(ai, rng, CharacterNameMaterialSerialized(
        kind=decided.kind, text=fixed.text, age=decided.age, parameters=parameters if person else None,
        born_location=material.born_location, avoided_names=material.resident_names,
        hint_name=form.name if form else None,
    ), person)
    subject = "人物" if person else "対象"
    name = draft.name if draft is not None else (form.name if form and form.name else subject)
    if isinstance(draft, PersonNameDraft):
        parameters.family_name = parameters.family_name or draft.family_name or None

    location_label = (f"{material.born_location.name}(id={material.born_location.id})" if material.born_location else "不明")
    logger.info(f"{material.time} 生成: {name} 種別={decided.kind} 出自={location_label} 年齢={decided.age}\n"
                f"    筋書きの要素: {material.element or '(無し)'}\n"
                + "".join(f"    ミーム: {drawn.position}: {drawn.text}\n" for drawn in material.memes))
    return CharacterCreation(
        name=name,
        kind=decided.kind,
        writing=_writing(fixed, material.memes, material.time, decided.age, name),
        main_character=bool(form and form.main_character),
        parameters=parameters,
        birth=Stamp(material.time.year - decided.age),
        # 死は先の出来事なので、作者が主要人物に決めて渡したときだけ持たせる(サブキャラクターには持たせない)
        end=form.end if form and form.main_character else None,
        born_location_id=born_location_id,
    )


def save_character(s: Session, creation: CharacterCreation) -> Character:
    record = Character(
        name=creation.name,
        kind=creation.kind,
        text=creation.writing.text,
        meme=creation.writing.meme,
        principle=creation.writing.principle,
        main_character=creation.main_character,
        end=creation.end,
        # 生まれた時点で決める値なので、誕生から効く一行だけを持つ
        parameters=[parameter_row(creation.parameters, creation.birth)],
    )
    record.histories = replaced_histories([], creation.writing.histories, CharacterHistory, owner=record)
    s.add(record)
    s.flush()
    if creation.born_location_id is not None:
        s.add(CharacterLocation(character_id=record.id, location_id=creation.born_location_id,
                                start=record.start, end=record.end))
    logger.info(f"足した: {record.name} id={record.id}")
    return record


def completion_target(s: Session, character_id: int) -> CompletionTarget:
    record = s.get_one(Character, character_id)
    if (record.text or "").strip():
        raise ValueError("text はすでに埋まっている")
    time = s.scalar(common_query.latest_time_select()) or record.start
    if time is None:
        raise ValueError("time が決められない(世界にまだ出来事が無く、record.start も空)")
    person = record.kind == CHARACTER_KIND_PERSON
    # 芯のほかに作者が書いた列は、核として渡す(ミーム・行動原理は引き直さずにそのまま残す)
    written = [f"{label}: {value.strip()}" for label, value in (
        ("外見", record.appearance), ("ミーム", record.meme), ("行動原理", record.principle), ("筋書き", record.plot))
        if value and value.strip()]
    return CompletionTarget(
        name=record.name, kind=record.kind, time=time, person=person,
        # locations は新しい順なので、末尾が生まれた場所
        born_location_id=record.locations[-1].location_id if record.locations else None,
        age=max(0, time.year - record.start.year) if record.start is not None else None,
        parameters=parameters_at(record, time) if person else None,
        hint_text="\n".join(written) or None,
    )


def completion_content(
    ai: AIClient, rng: random.Random, target: CompletionTarget, sources: BirthSources,
) -> tuple[CharacterBirthMaterialSerialized, PersonContentDraft | NonPersonContentDraft]:
    """決まっている名前・属性・出自と、作者が書いた外見・ミーム・行動原理・筋書きを核に、説明と来歴だけを AI に書かせる。"""
    material = _birth_material(
        ai, rng, sources, target.time, target.person, target.parameters, target.name,
        None if target.person else target.kind, target.age, None, target.hint_text, None, None, draw_memes=False)
    subject = "人物" if target.person else "対象"
    content = _content(ai, material, f"この{subject}の説明を決めてください。")
    if content is None:
        raise ValueError("説明が得られなかった")
    return material, content


def completed_text(
    ai: AIClient, target: CompletionTarget, material: CharacterBirthMaterialSerialized,
    content: PersonContentDraft | NonPersonContentDraft, ideas: IdeaContextMaterial,
) -> CharacterWriting:
    # 生年の無い人物も、AI が決めた歳で来歴の年を割り出す(生年そのものは変えない)
    age = target.age if target.age is not None else content.age
    fixed = reconciled(ai, material, target.kind, age, content, ideas)
    return _writing(fixed, material.memes, target.time, age, target.name)


def save_completed_text(s: Session, character_id: int, writing: CharacterWriting) -> Character:
    """芯を書き、来歴の節目は今の行に足す(同じ年の行があればその説明に書き足す)。ほかの列は変えない。"""
    record = s.get_one(Character, character_id)
    record.text = writing.text
    for row in writing.histories:
        if row.start is not None:
            add_history(record, row.start, row.description)
    s.flush()
    return record
