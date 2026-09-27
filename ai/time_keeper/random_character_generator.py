#!/usr/bin/env python3
from __future__ import annotations

import random

from sqlalchemy import and_, func, select, union, union_all
from sqlalchemy.orm import aliased

from ai.instructions.naming import (
    CHARACTER_NAMING_INSTRUCTION, NAME_PLACEHOLDER, IDEA_NAMING_INSTRUCTION,
    fill_name_placeholder,
)
from data_access_logic.query import (
    common_query, dictionary_query, story_createion_query, world_createion_query,
)
from data_access_logic.query.base import *
from db.schema import *
from db.schema import PERSON_PARAMETER_COLUMNS, PERSONALITY_COLUMNS, PERSONALITY_LEVELS
from db.child_lists import load_children
from ai.time_keeper._ai import AIClient
from ai.time_keeper import constants, idea_context, meme
from ai.time_keeper._format import format_time
from randomizer.random_character_generator import build_character

_PLACEHOLDER_INSTRUCTION = (
    f"この一件の名前はまだ決まっていない。text の中でこの一件を指すときは必ず「{NAME_PLACEHOLDER}」と書き、名前を考案して書き込まない。"
)

_AGE_RANGE = f"{constants.GENERATION_CHARACTER_AGE_RANGE[0]}〜{constants.GENERATION_CHARACTER_AGE_RANGE[1]}"


_LATER_INSTRUCTION = (
    "筋書きや既にいる人物・対象の説明は、現在の時刻より後の姿で書かれていることがある。"
    "「この時刻より後に始まる設定」が渡されているときは、それはまだ世に無い。その設定に当たる立場・仕事・組織・技術・出来事を、"
    "来歴にも現在の姿にも出さず、既にいる人物の説明に出てきても、この時刻にはまだ無いものとして扱う。"
)


def _meme_instruction(subject: str) -> str:
    return (
        f"「この{subject}の行動原理(ミーム)」が渡されているときは、それぞれに振られた古今表裏({meme.position_legend()})を変えずに、"
        f"ミームどうしの関係を整理して principle に書いてください。何を経て古いものを手放したか、表と裏がどう食い違い、"
        f"この{subject}の中でどう折り合っているかを、出来事や人との関わりとして書く。食い違うミームも、どちらかを捨てずに両方を生かす。"
        f"ミームの文面をそのまま書き写さない。text もこの整理と矛盾させない。"
    )


_CONTENT_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
新しく生まれる人物1件について、人物説明・年齢を、自然な日本語で JSON で答えてください。
渡す場所の説明・参考地域・参考文化・参考時代や、所属する地域、その場所・時刻に関連する筋書きに、この人物の生活・仕事・性格が自然に馴染むよう考慮してください(参考地域・参考文化・参考時代は、固有名詞をそのまま持ち込むのではなく、地理・気候・生業・価値観の手がかりとして使ってください)。
「この人物が体現する要素」が渡されているときは、複数の立場のうちあなたが選びやすいものへ寄せず、渡された要素をこの人物の生き方の核として必ず反映してください。
「既にいる人物・対象」が渡されているときは、その役割・関係・特徴とは重ならない人物にしてください(同じ立場・同じ能力・同じ関係性の作り直しをしない)。
{_LATER_INSTRUCTION}
「性格」は各軸を {'/'.join(PERSONALITY_LEVELS)} の五段階で渡す(サイコロで決まっていて変えられない)。人物説明はこの段階と矛盾しないようにし、「無」「必」の軸はその極端さが生活・仕事・人との関わり方に具体的な癖として表れるように書く。段階の語をそのまま書き写さない。
{_meme_instruction("人物")}
{_PLACEHOLDER_INSTRUCTION}
キーは次の五つだけ。
- text: 具体的な生活・仕事・関係が伝わる2〜3文の人物説明。目立った能力・特技があれば地の文として含め、別項目には分けない。「優しい」「謎めいた」のような、誰にでも当てはまる抽象的な形容だけで済ませず、この人物固有の具体的な癖・関わり・生い立ちを最低一つ含める。
- age: 年齢(整数)。{_AGE_RANGE}の範囲で、text の人物説明と矛盾しない値をあなた自身で決める。例えば老成した説明なら年長めに、幼さの残る説明なら年少めに。
- principle: 行動原理(ミーム)どうしの関係を整理した2〜4文。ミームが渡されていなければ空文字。
- dialect: 方言。出身地・参考地域・参考文化・生業・生い立ち・年齢・性格・口調から、この人物がどんな言葉で話すかを1〜2文で決める。土地の言葉で話すなら、どの地方風の方言か(現実の方言を手本にしてよい)と、特徴的な語尾・言い回しを一つ以上。標準語で話すなら、その人物らしい癖(語尾・口ぐせ・言い淀み・訛りの名残など)を一つ以上。誰にでも当てはまる「普通の話し方」で済ませない。
- history: 来歴。生まれてから age の歳までの節目を、歳の順に3〜5件。各要素は age(その時の歳。0 以上、上の age 以下の整数)と text(その歳に何があり、立場・仕事・住まい・人間関係がどう変わったかの1文)。人物説明の立場・仕事・住まいには、いつそうなったかの節目を必ず含める。"""

_CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "age": {"type": "integer", "minimum": constants.GENERATION_CHARACTER_AGE_RANGE[0], "maximum": constants.GENERATION_CHARACTER_AGE_RANGE[1]},
        "principle": {"type": "string"},
        "dialect": {"type": "string"},
        "history": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "age": {"type": "integer", "minimum": 0,
                            "maximum": constants.GENERATION_CHARACTER_AGE_RANGE[1]},
                    "text": {"type": "string"},
                },
                "required": ["age", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["text", "age", "principle", "dialect", "history"],
    "additionalProperties": False,
}

_NON_PERSON_CONTENT_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
ある場所と、そこに居る人物・既にある対象を渡すので、この場所を拠り所に生まれる人物以外の対象(国・組織・商会・氏族・集団など、まとまりとして動くもの。あるいは物)を1件だけ考え、JSON で答えてください。
渡す場所の産業・地形・人間関係のうち少なくとも一つを具体的に使う。
「この対象が体現する要素」が渡されているときは、渡された要素をこの対象の成り立ちの核として必ず反映してください。
既にある対象と役割が重なるものは作らない。
{_LATER_INSTRUCTION}
{_meme_instruction("対象")}
{_PLACEHOLDER_INSTRUCTION}
キーは次の四つだけ。
- kind: 種別。{' / '.join(constants.NON_PERSON_KINDS)} のいずれか一つ。
- text: この対象が何であって、何を決められて、誰に対して力を持つのかが伝わる2〜3文の説明。「由緒ある」「謎めいた」のような、どの対象にも当てはまる形容だけで済ませない。
- age: 成り立ってからの年数(整数)。{_AGE_RANGE}の範囲。
- principle: 行動原理(ミーム)どうしの関係を整理した2〜4文。ミームが渡されていなければ空文字。"""

_NON_PERSON_CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(constants.NON_PERSON_KINDS)},
        "text": {"type": "string"},
        "age": {"type": "integer", "minimum": constants.GENERATION_CHARACTER_AGE_RANGE[0], "maximum": constants.GENERATION_CHARACTER_AGE_RANGE[1]},
        "principle": {"type": "string"},
    },
    "required": ["kind", "text", "age", "principle"],
    "additionalProperties": False,
}

_NAME_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
内容が決まっている人物1件に、名前と名字を付けます。
{CHARACTER_NAMING_INSTRUCTION}
渡す人物説明・年齢・体格や口調から連想できる、この人物に似合う名前にしてください。
居場所・場所の特徴・所属する地域が渡されているときは、その参考地域・参考文化・参考時代を名の響きや漢字・カタカナの選び方の手がかりにして、同じ場所の人物として馴染む名にしてください(固有名詞をそのまま持ち込まない)。
名字は、生まれたときに名乗るものを、出身地・身分・家業・参考文化から決める。その土地・身分で名字を持たないのが自然なら空文字にする。
キーは name(名字を含めない名)と family_name(名字)の二つ。"""

_NON_PERSON_NAME_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
内容が決まっている人物以外の対象(国・組織・集団・物など)1件に、名前だけを付けます。
{IDEA_NAMING_INSTRUCTION}
組織の名は場所名か役割名で呼べる形にする。
居場所・場所の特徴・所属する地域が渡されているときは、その参考地域・参考文化・参考時代を名の響きや漢字・カタカナの選び方の手がかりにして、同じ場所のものとして馴染む名にしてください(固有名詞をそのまま持ち込まない)。
「既にいる人物・対象の名」が渡されているときは、それらと紛らわしい名にしない。
キーは name(名前)だけ。"""

_POLISH_SYSTEM_PROMPT = f"""\
あなたは架空の世界観を構築する設定作家です。
決まったばかりの人物・対象の説明(下書き)と、その下書きに関係する設定を渡すので、設定を踏まえて説明を清書してください。
下書きの人物像・生い立ち・関係・長さは変えない。設定と食い違うところ、設定を踏まえると具体的にできるところだけを直す。
{_PLACEHOLDER_INSTRUCTION}
キーは text(清書した説明)だけ。"""

_POLISH_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}

_NAME_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
    },
    "required": ["name"],
    "additionalProperties": False,
}

_PERSON_NAME_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "family_name": {"type": "string"},
    },
    "required": ["name", "family_name"],
    "additionalProperties": False,
}

def history_section(items, born_year: int, age: int) -> str:
    rows = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        try:
            at = int(item.get("age"))
        except (TypeError, ValueError):
            continue
        if text and 0 <= at <= age:
            rows.append((at, text))
    rows.sort(key=lambda row: row[0])
    return "\n".join(f"- {born_year + at}年({at}歳): {text}" for at, text in rows)


def _should_roll(time: Stamp) -> bool:
    return time.day == 1


def _personality_label(values) -> str:
    get = values.get if hasattr(values, "get") else (lambda column: getattr(values, column))
    columns = CharacterParameter.__table__.columns
    return " / ".join(f"{columns[column].comment}={get(column)}" for column in PERSONALITY_COLUMNS)


def _region_label(session: Session, born_place: Location | None) -> str:
    if born_place is None or born_place.parent_id is None:
        return "不明"
    parent = session.get(Location, born_place.parent_id)
    if parent is None:
        return "不明"
    return f"{parent.name}({parent.kind})"


def _story_text(session: Session, born_place: Location | None, time: Stamp) -> str:
    if born_place is None:
        return ""
    return story_createion_query.load_location_story_text(session, born_place.id, time)


_ELEMENT_SYSTEM_PROMPT = """\
あなたは筋書きの構成を分析する設定作家です。
渡す筋書きの本文から、その筋書きの中で人物が生きうる、互いに重ならない具体的な立場・職業・関わり方を箇条書きで抜き出してください。
筋書きが複数の立場を挙げている場合は、それぞれを一つずつの要素にして漏らさず拾ってください。
筋書きに出てくる特定の人物(主人公やその家族・仲間など)が担う役どころそのものは抜き出さないでください。その人物の写しになってしまうため、同じ筋書きの世界で別の人物が就きうる立場として書いてください。
筋書きは時の流れをまたいで書かれている。渡す現在の時刻にまだ始まっていない立場(筋書きの中で後の年に起きる出来事や、「この時刻より後に始まる設定」を前提にする立場)は抜き出さないでください。
キーは elements(文字列の配列)だけです。"""

_ELEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "elements": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["elements"],
    "additionalProperties": False,
}


def _story_elements(story_text: str, time: Stamp, later_label: str, ai: AIClient) -> list[str]:
    """抜き出し(この関数)と選択(呼び出し側の `rng.choice`)を分けることで、
    複数の立場を持つ筋書きでも生成のたびランダムに割り振られるようにし、
    モデルが生成時に自由選択して同じ立場へ偏るのを防ぐ。
    """
    if not story_text:
        return []
    decided = ai.try_generate_json(
        f"現在の時刻: {time}\n{later_label}筋書き:\n{story_text}", _ELEMENT_SCHEMA, system=_ELEMENT_SYSTEM_PROMPT)
    return [e.strip() for e in decided.get("elements", []) if e and e.strip()]


def _nearby_place_ids(session: Session, born_place: Location | None) -> list[int]:
    if born_place is None:
        return []
    return [node["id"] for node in common_query.place_path(session, born_place.id)]


def _nearby_characters(session: Session, born_place: Location | None, time: Stamp) -> list[Character]:
    """件数は `constants.NEARBY_CHARACTER_LIMIT` まで(祖先をたどるほど無際限に増えるため)。"""
    place_ids = _nearby_place_ids(session, born_place)
    if not place_ids:
        return []
    ids = session.scalars(common_query.resident_character_ids_select(place_ids, time)).all()
    if not ids:
        return []
    ids = ids[:constants.NEARBY_CHARACTER_LIMIT]
    return list(session.scalars(select(Character).where(Character.id.in_(ids))).all())


def _later_ideas_label(session: Session, born_place: Location | None, time: Stamp) -> str:
    if born_place is None:
        return ""
    ideas = session.scalars(dictionary_query.later_ideas_select(
        common_query.idea_scope_ids(session, born_place.id), time)).all()
    if not ideas:
        return ""
    lines = []
    for idea in ideas:
        text = (idea.text or "").strip()
        if len(text) > constants.IDEA_CONTEXT_LETTERS:
            text = text[:constants.IDEA_CONTEXT_LETTERS] + "…"
        lines.append(f"- {idea.name}({idea.kind}。{idea.start.year}年から): {text}")
    return "この時刻より後に始まる設定(まだ無い):\n" + "\n".join(lines) + "\n"


def _record_context(records: list[Character]) -> str:
    if not records:
        return "(無し)"
    return "\n".join(f"- {r.name}({r.kind}): {r.text or '(説明なし)'}" for r in records)


def _character_names(characters: list[Character]) -> str:
    if not characters:
        return "(無し)"
    return "、".join(c.name or "" for c in characters)


def _location_context(place: Location | None) -> str:
    if place is None:
        return "(不明)"
    lines = [place.text or "(説明なし)"]
    references = [
        label for label in (
            f"参考地域: {place.sample_region}" if place.sample_region else None,
            f"参考文化: {place.sample_culture}" if place.sample_culture else None,
            f"参考時代: {place.sample_era}" if place.sample_era else None,
        ) if label
    ]
    if references:
        lines.append(" / ".join(references))
    return "\n".join(lines)


def _hint_line(hints: dict, subject: str) -> str:
    """作者が下書きに書いた名前・説明を、決めるときの核として渡す。書き方は AI に任せる(そのまま写させない)。"""
    given = {label: (hints.get(key) or "").strip() for key, label in (("name", "名前"), ("text", "説明"))}
    given = {label: value for label, value in given.items() if value}
    if not given:
        return ""
    return (f"作者の指定(この{subject}の核にする。足りないところを補い、言い回しは変えてよい): "
            + " / ".join(f"{label}: {value}" for label, value in given.items()) + "\n")


def _apply_parameter_hints(parameters: dict, hints: dict) -> None:
    """作者が決めた性別・体格・口調・性格などはサイコロの値より優先する。"""
    rows = hints.get("parameters") or []
    row = rows[0] if isinstance(rows, list) and rows else (rows if isinstance(rows, dict) else {})
    for column, value in row.items():
        if column in parameters and value not in (None, ""):
            parameters[column] = value


def complete_text(session: Session, record: Character, born_place: Location | None, ai: AIClient) -> str:
    """人物・対象の本文(text)が空のとき、決まっている名前・属性・出自を核に AI に本文だけを書かせて返す
    (db は触らない。呼び出し側が `record.text` に入れて確定する)。
    性別・体格・口調・性格・種別・生年・没年・名前は変えない(`_generate_one` と違い、ここでは組み立て直さない)。"""
    time = session.scalar(common_query.latest_time_select()) or record.start
    if time is None:
        raise ValueError("time が決められない(世界にまだ出来事が無く、record.start も空)")
    person = record.kind == CHARACTER_KIND_PERSON
    parameters = record.parameters_at(time) if person else {}
    age = max(0, time.year - record.start.year) if record.start is not None else None

    region_label = _region_label(session, born_place)
    story_text = _story_text(session, born_place, time)
    story_label = story_text or "(無し)"
    later_label = _later_ideas_label(session, born_place, time)
    elements = _story_elements(story_text, time, later_label, ai)
    rng = random.Random()
    chosen_element = rng.choice(elements) if elements else None
    subject = "人物" if person else "対象"
    element_line = f"この{subject}が体現する要素: {chosen_element}\n" if chosen_element else ""

    drawn_memes = meme.draw(
        session, rng, constants.MEME_PERSON_CATEGORIES if person else constants.MEME_NON_PERSON_CATEGORIES)
    meme_line = (
        f"この{subject}の行動原理(ミーム。{meme.position_legend()}):\n{meme.meme_section(drawn_memes)}\n"
        if drawn_memes else ""
    )

    nearby_characters = _nearby_characters(session, born_place, time)
    person_line = (
        f"性別: {parameters.get('sex')} / 体格: {parameters.get('build')} / 口調: {parameters.get('tone')}\n"
        f"性格({'/'.join(PERSONALITY_LEVELS)} の五段階): {_personality_label(parameters)}\n"
        if person and parameters else ""
    )
    name_line = f"名前(決まっている): {record.name}\n" if record.name else ""
    kind_line = f"種別(決まっている): {record.kind}\n" if not person else ""
    age_line = f"年齢(決まっている。age はこの値にする): {age}\n" if age is not None else ""

    content_prompt = (
        f"{name_line}"
        f"出身: {born_place.name if born_place else '不明'}\n"
        f"出身地の特徴:\n{_location_context(born_place)}\n"
        f"地域: {region_label}\n"
        f"{kind_line}"
        f"{person_line}"
        f"{age_line}"
        f"現在の時刻: {time}\n"
        f"この場所・時刻に関連する筋書き:\n{story_label}\n"
        f"{later_label}"
        f"{element_line}"
        f"{meme_line}"
        f"既にいる人物・対象:\n{_record_context(nearby_characters)}\n"
        f"この{subject}の本文(説明)を決めてください。"
    )
    if person:
        decided = ai.try_generate_json(content_prompt, _CONTENT_SCHEMA, system=_CONTENT_SYSTEM_PROMPT)
    else:
        decided = ai.try_generate_json(
            content_prompt, _NON_PERSON_CONTENT_SCHEMA, system=_NON_PERSON_CONTENT_SYSTEM_PROMPT)

    text = (decided.get("text") or "").strip()
    context = idea_context.gather(session, text, ai, born_place.id if born_place else None, time)
    if context.related:
        polished = ai.try_generate_json(
            f"下書き: {text}\n{idea_context.prompt_section(context.related, context.called, time)}この説明を清書してください。",
            _POLISH_SCHEMA, system=_POLISH_SYSTEM_PROMPT, timeout=constants.IDEA_POLISH_TIMEOUT)
        text = (polished.get("text") or "").strip() or text
    if person and age is not None:
        text += f"\n\n# 来歴\n{history_section(decided.get('history'), time.year - age, age)}"
    if drawn_memes:
        text += f"\n\n# meme\n{meme.meme_section(drawn_memes)}"
        principle = (decided.get("principle") or "").strip()
        if principle:
            text += f"\n\n# 行動原理\n{principle}"
    text = fill_name_placeholder(text, record.name or "")
    idea_context.link(session, record, context.linked)
    return text


def _generate_one(
    session: Session, born_place: Location | None, time: Stamp, rng: random.Random,
    ai: AIClient, person: bool = True, hints: dict | None = None,
) -> Character:
    """`hints` は作者の下書き(GUI の欄の値)。名前・説明は核として AI に渡し、性別・体格・口調・性格・
    種別・生年・没年・メインキャラクターかは決まった値として使う。渡された欄もすべて AI が組み立て直す。"""
    hints = dict(hints or {})
    draft = build_character()
    # 生まれた時点で決める値なので、期間を限らない一行だけを持つ
    parameters = draft["parameters"][0]
    _apply_parameter_hints(parameters, hints)
    if not person:
        for column in PERSON_PARAMETER_COLUMNS:
            parameters[column] = None
        if hints.get("kind") in constants.NON_PERSON_KINDS:
            draft["kind"] = hints["kind"]
    if hints.get("main_character") is not None:
        draft["main_character"] = bool(hints["main_character"])
    birth = Stamp.parse(hints.get("start"))
    fixed_age = max(0, time.year - birth.year) if birth is not None else None

    region_label = _region_label(session, born_place)
    story_text = _story_text(session, born_place, time)
    story_label = story_text or "(無し)"

    later_label = _later_ideas_label(session, born_place, time)
    elements = _story_elements(story_text, time, later_label, ai)
    chosen_element = rng.choice(elements) if elements else None
    subject = "人物" if person else "対象"
    element_line = (
        f"この{subject}が体現する要素: {chosen_element}\n"
        if chosen_element else ""
    )

    drawn_memes = meme.draw(
        session, rng, constants.MEME_PERSON_CATEGORIES if person else constants.MEME_NON_PERSON_CATEGORIES)
    meme_line = (
        f"この{subject}の行動原理(ミーム。{meme.position_legend()}):\n{meme.meme_section(drawn_memes)}\n"
        if drawn_memes else ""
    )

    nearby_characters = _nearby_characters(session, born_place, time)
    person_line = (
        f"性別: {parameters['sex']} / 体格: {parameters['build']} / 口調: {parameters['tone']}\n"
        f"性格({'/'.join(PERSONALITY_LEVELS)} の五段階): {_personality_label(parameters)}\n"
        if person else ""
    )

    kind_line = f"種別(決まっている): {draft['kind']}\n" if not person and hints.get("kind") in constants.NON_PERSON_KINDS else ""
    age_line = f"年齢(決まっている。age はこの値にする): {fixed_age}\n" if fixed_age is not None else ""
    content_prompt = (
        f"出身: {born_place.name if born_place else '不明'}\n"
        f"出身地の特徴:\n{_location_context(born_place)}\n"
        f"地域: {region_label}\n"
        f"{kind_line}"
        f"{person_line}"
        f"{age_line}"
        f"現在の時刻: {time}\n"
        f"この場所・時刻に関連する筋書き:\n{story_label}\n"
        f"{later_label}"
        f"{element_line}"
        f"{meme_line}"
        f"{_hint_line(hints, subject)}"
        f"既にいる人物・対象:\n{_record_context(nearby_characters)}\n"
        f"この場所に自然な{subject}を1件、決めてください。"
    )
    if person:
        decided = ai.try_generate_json(
            content_prompt, _CONTENT_SCHEMA, system=_CONTENT_SYSTEM_PROMPT)
    else:
        decided = ai.try_generate_json(
            content_prompt, _NON_PERSON_CONTENT_SCHEMA, system=_NON_PERSON_CONTENT_SYSTEM_PROMPT)
        if hints.get("kind") not in constants.NON_PERSON_KINDS:
            kind = decided.get("kind")
            draft["kind"] = kind if kind in constants.NON_PERSON_KINDS else rng.choice(constants.NON_PERSON_KINDS)

    draft["text"] = decided.get("text") or draft["text"]
    if person:
        parameters["dialect"] = (decided.get("dialect") or "").strip() or None
    context = idea_context.gather(session, draft["text"], ai, born_place.id if born_place else None, time)
    if context.related:
        polished = ai.try_generate_json(
            f"下書き: {draft['text']}\n{idea_context.prompt_section(context.related, context.called, time)}この説明を清書してください。",
            _POLISH_SCHEMA, system=_POLISH_SYSTEM_PROMPT, timeout=constants.IDEA_POLISH_TIMEOUT)
        draft["text"] = (polished.get("text") or "").strip() or draft["text"]
    try:
        age = int(decided.get("age", 0))
    except (TypeError, ValueError):
        age = rng.randint(*constants.GENERATION_CHARACTER_AGE_RANGE)
    age = min(max(age, constants.GENERATION_CHARACTER_AGE_RANGE[0]), constants.GENERATION_CHARACTER_AGE_RANGE[1])
    if fixed_age is not None:
        age = fixed_age

    if person:
        draft["text"] += f"\n\n# 来歴\n{history_section(decided.get('history'), time.year - age, age)}"
    if drawn_memes:
        draft["text"] += f"\n\n# meme\n{meme.meme_section(drawn_memes)}"
        principle = (decided.get("principle") or "").strip()
        if principle:
            draft["text"] += f"\n\n# 行動原理\n{principle}"

    birth = Stamp(time.year - age)
    # 死亡していない対象の end は空にする(自然死は character_lifespan が別に判定して書き込む)
    death = Stamp.parse(hints.get("end"))

    dialect_line = f"方言: {parameters['dialect']}\n" if person and parameters.get("dialect") else ""
    # 名前は、説明・年齢など中身が決まったあとに、その内容から連想して決める。
    name_prompt = (
        f"種別: {draft['kind']}\n"
        f"説明: {draft['text']}\n"
        f"年齢: {age}\n"
        f"{person_line}"
        f"{dialect_line}"
        f"居場所: {born_place.name if born_place else '不明'}\n"
        f"場所の特徴:\n{_location_context(born_place)}\n"
        f"所属する地域: {region_label}\n"
        f"既にいる人物・対象の名: {_character_names(nearby_characters)}\n"
        + (f"作者が付けたい名: {hints['name'].strip()}(この{subject}に似合うならこれを使い、合わなければ近い響きにする)\n"
           if (hints.get("name") or "").strip() else "")
        + f"この{subject}に似合う名前を決めてください。"
    )
    if person:
        named = ai.try_generate_json(name_prompt, _PERSON_NAME_SCHEMA, system=_NAME_SYSTEM_PROMPT)
        parameters["family_name"] = (named.get("family_name") or "").strip() or None
    else:
        named = ai.try_generate_json(name_prompt, _NAME_SCHEMA, system=_NON_PERSON_NAME_SYSTEM_PROMPT)
    draft["name"] = named.get("name") or draft["name"]
    draft["text"] = fill_name_placeholder(draft["text"], draft["name"])

    record = Character(**{key: value for key, value in draft.items() if key != "parameters"},
                       confirmed=ConfirmStatus.PENDING)
    load_children(record, "parameters", draft["parameters"])
    record.start = birth
    record.end = death
    session.add(record)
    session.flush()  # place から character_id で参照するため、先に id を確定する

    if born_place is not None:
        session.add(CharacterPlace(
            character_id=record.id, location_id=born_place.id,
            start=record.start, end=record.end))
    idea_context.link(session, record, context.linked)

    session.commit()
    when = format_time(time)
    place_label = f"{born_place.name}(id={born_place.id})" if born_place else "不明"
    print(f"[time_keepr/character] {when} 生成: {record.name}"
          f" id={record.id} 種別={record.kind} 出自={place_label} 年齢={age}\n"
          + (f"    名字: {parameters['family_name'] or '(無し)'}\n"
             f"    性別: {parameters['sex']} / 体格: {parameters['build']} / 口調: {parameters['tone']}\n"
             f"    方言: {parameters['dialect']}\n"
             f"    性格: {_personality_label(parameters)}\n"
             if person else "")
          + f"    筋書きの要素: {chosen_element or '(無し)'}\n"
          + "".join(f"    ミーム: {item['position']}: {item['text']}\n" for item in drawn_memes)
          + f"    説明: {record.text or '(説明なし)'}")
    return record


def get_usable_location_q(time: Stamp):
    base_q = (
        select(Location.id)
        .outerjoin(
            CharacterPlace,
            and_(CharacterPlace.location_id == Location.id),
        )
        .outerjoin(
            Character, Character.id == CharacterPlace.character_id
        )
        .where(
            location_active_condition(time),
        )
    )

    q_1 = (
        base_q
        .where(
            Character.id == None,
        )
    )

    q_2 = (
        base_q
        .where(
            character_time_condition(time)
        )
        .group_by(Location.id)
        .having(
            func.count(Character.id.distinct()) < constants.MAX_CHARACTER_PER_LOCATION
        )
    )

    return union_all(q_1, q_2)


def generate_random(session: Session, time: Stamp, ai: AIClient) -> Character | None:
    usable_location_q = get_usable_location_q(time)
    eligible_places = session.scalars(select(Location).where(Location.id.in_(usable_location_q))).all()
    if not eligible_places:
        print(f"[time_keepr/character] 空きのある場所が無いため見送り")
        return None

    for location in eligible_places:
        try_generate_character(
            session, time, location, ai
        )


def try_generate_character(
    session: Session,
    time: Stamp,
    location: Location,
    ai: AIClient,
):
    if not _should_roll(time):
        return None

    seed = random.randrange(10 ** 9)
    rng = random.Random(seed)
    roll = rng.random()
    when = format_time(time)

    if roll >= constants.GENERATION_CHARACTER_PROBABILITY:
        print(f"[time_keepr/character] {when} 判定: "
              f"seed={seed} roll={roll:.4f} >= {constants.GENERATION_CHARACTER_PROBABILITY} → 見送り")
        return None
    print(f"[time_keepr/character] {when} 判定: "
          f"seed={seed} roll={roll:.4f} < {constants.GENERATION_CHARACTER_PROBABILITY} → 生成")

    # 人物か、人物以外の対象か。数の偏りは AI に任せずサイコロで決める。
    person = rng.random() >= constants.NON_PERSON_PROBABILITY
    print(f"[time_keepr/character] {when} 種別判定: {'人物' if person else '人物以外の対象'}")

    return _generate_one(session, location, time, rng, ai, person=person)
