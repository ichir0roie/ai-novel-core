from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from data_access_logic import constants
from data_access_logic.character.histories import histories_for_prompt
from data_access_logic.character.form import CharacterParameterForm
from data_access_logic.character.models import CharacterBase, CharacterParameterValues
from data_access_logic.character.record import CharacterHistoryRow
from data_access_logic.idea.models import IdeaMaterial
from data_access_logic.location.models import LocationMaterial, LocationTextMaterial
from data_access_logic.material import Material
from data_access_logic.meme.models import DrawnMeme, PooledMeme
from data_access_logic.story.models import StoryPlotMaterial
from db.schema import PersonalityLevel
from db.stamp import Stamp

_AGE_RANGE = constants.GENERATION_CHARACTER_AGE_RANGE
_SCENE_AGE_RANGE = constants.SCENE_CHARACTER_AGE_RANGE


class BirthLocationMaterial(LocationTextMaterial):
    sample_region: str | None = None
    sample_culture: str | None = None
    sample_era: str | None = None
    parent: LocationMaterial | None = None


class NearbyCharacter(CharacterBase):
    # 生む時刻までに起きた来歴(`histories_at`)
    histories: list[CharacterHistoryRow]


class CharacterBirthMaterial(Material):
    time: Stamp
    person: bool
    born_location: BirthLocationMaterial | None = None
    # 上位の場所のものから順
    stories: list[StoryPlotMaterial]
    # この時刻より後に始まる、まだ世に無い設定
    later_ideas: list[IdeaMaterial]
    # 筋書きから抜き出した立場のうち、サイコロで選んだもの
    element: str | None = None
    memes: list[DrawnMeme]
    nearby_characters: list[NearbyCharacter]
    # 同じ場所にいる人物・対象の名。中身の段には渡さず、名付けで避ける
    resident_names: list[str]
    # 人物なら、作者の指定(芯を埋めるときは今の値)で決まっている値。決まっていない値は None で、AI が決める
    parameters: CharacterParameterForm | None = None
    # 以下は決まっている値。None なら AI が決める
    name: str | None = None
    kind: str | None = None
    age: int | None = None
    # 作者が下書きに書いた名前・説明。核にするが言い回しは変えてよい
    hint_name: str | None = None
    hint_text: str | None = None
    # この人物を登場させる話のプロット。年齢を、この時刻・場所でその役どころを果たせる値にする手がかり
    plot_text: str | None = None


def _born_location(born_location: BirthLocationMaterial | None) -> dict[str, Any] | None:
    if born_location is None:
        return None
    return {
        "名前": born_location.name,
        "種別": born_location.kind,
        "説明": born_location.text,
        "参考地域": born_location.sample_region,
        "参考文化": born_location.sample_culture,
        "参考時代": born_location.sample_era,
        "所属する地域": (f"{born_location.parent.name}({born_location.parent.kind})"
                         if born_location.parent else None),
    }


PERSONALITY_LABELS = {
    "sincerity": "誠実性",
    "curiosity": "好奇心",
    "proactivity": "行動力",
    "cooperativeness": "協調性",
    "sociability": "社交性",
    "emotional_expression": "感情表現",
    "self_esteem": "自己肯定感",
    "self_efficacy": "自己効力感",
    "stress_resilience": "ストレス耐性",
    "flexibility_of_values": "価値観の柔軟性",
    "sensitivity": "感受性",
    "imagination": "想像力",
}


def _personality(parameters: CharacterParameterValues | CharacterParameterForm) -> dict[str, str] | None:
    """決まっている軸だけ(どれも決まっていなければ None)。"""
    axes = {label: getattr(parameters, name) for name, label in PERSONALITY_LABELS.items()
            if getattr(parameters, name) is not None}
    return axes or None


class CharacterBirthMaterialSerialized(CharacterBirthMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        parameters = self.parameters
        return {
            "現在の時刻": str(self.time),
            "出身": _born_location(self.born_location),
            "この場所・時刻に関連する筋書き": "\n\n".join(story.text for story in self.stories if story.text) or None,
            "この時刻より後に始まる設定(まだ無い)": [
                {"名前": idea.name, "種類": idea.kind, "始まる年": idea.start.year if idea.start else None}
                for idea in self.later_ideas],
            "体現する要素": self.element,
            "行動原理(ミーム)": [{"古今表裏": meme.position, "内容": meme.text} for meme in self.memes],
            "既にいる人物・対象": [
                {"名前": character.name, "種別": character.kind, "説明": character.text,
                 "来歴(古い順)": histories_for_prompt(character.histories)}
                for character in self.nearby_characters],
            "決まっている": {
                "名前": self.name,
                "種別": self.kind,
                "年齢": self.age,
                "性格": _personality(parameters) if parameters else None,
                "性別": parameters.sex if parameters else None,
                "背丈": parameters.height if parameters else None,
                "体格": parameters.build if parameters else None,
                "一人称": parameters.first_person if parameters else None,
                "二人称": parameters.second_person if parameters else None,
                "三人称": parameters.third_person if parameters else None,
                "口調": parameters.tone if parameters else None,
                "方言": parameters.dialect if parameters else None,
            },
            "作者の指定": {"名前": self.hint_name, "説明": self.hint_text},
            "登場する話のプロット": self.plot_text,
        }


class CharacterNameMaterial(Material):
    kind: str
    text: str
    age: int
    parameters: CharacterParameterValues | None = None
    born_location: BirthLocationMaterial | None = None
    # 同じ場所(居場所とその上位・配下)にいる人物・対象の名。名付けで避ける
    avoided_names: list[str]
    hint_name: str | None = None


class CharacterNameMaterialSerialized(CharacterNameMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        parameters = self.parameters
        return {
            "種別": self.kind,
            "説明": self.text,
            "年齢": self.age,
            "性格": _personality(parameters) if parameters else None,
            "性別": parameters.sex if parameters else None,
            "背丈": parameters.height if parameters else None,
            "体格": parameters.build if parameters else None,
            "一人称": parameters.first_person if parameters else None,
            "二人称": parameters.second_person if parameters else None,
            "三人称": parameters.third_person if parameters else None,
            "口調": parameters.tone if parameters else None,
            "方言": parameters.dialect if parameters else None,
            "決まっている名字": parameters.family_name if parameters else None,
            "居場所": _born_location(self.born_location),
            "同じ場所にいる人物・対象の名": self.avoided_names,
            "作者が付けたい名": self.hint_name,
        }


# 年齢の幅(人物の生成とプロットの役どころで違う)は、決まった年齢がある場合もあるので schema では限らず、
# 呼ぶ側で丸める(`generator._person_age`)。負の値だけはここで 0 にする
def _not_negative(value: Any) -> Any:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return value


class StoryElementsDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    elements: list[str] = Field(description="筋書きの中で人物が生きうる、互いに重ならない具体的な立場・職業・関わり方")

    @field_validator("elements")
    @classmethod
    def _filled(cls, value: list[str]) -> list[str]:
        return [element.strip() for element in value if element.strip()]


class HistoryItemDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age: int = Field(ge=0, description="その時の歳")
    text: str = Field(description="その歳に何があり、立場・仕事・住まい・人間関係がどう変わったかの1文")

    @field_validator("age", mode="before")
    @classmethod
    def _age(cls, value: Any) -> Any:
        return _not_negative(value)


class PersonalityDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sincerity: PersonalityLevel = Field(description="誠実性")
    curiosity: PersonalityLevel = Field(description="好奇心")
    proactivity: PersonalityLevel = Field(description="行動力")
    cooperativeness: PersonalityLevel = Field(description="協調性")
    sociability: PersonalityLevel = Field(description="社交性")
    emotional_expression: PersonalityLevel = Field(description="感情表現")
    self_esteem: PersonalityLevel = Field(description="自己肯定感")
    self_efficacy: PersonalityLevel = Field(description="自己効力感")
    stress_resilience: PersonalityLevel = Field(description="ストレス耐性")
    flexibility_of_values: PersonalityLevel = Field(description="価値観の柔軟性")
    sensitivity: PersonalityLevel = Field(description="感受性")
    imagination: PersonalityLevel = Field(description="想像力")


_PERSON_AGE_DESCRIPTION = (
    "現在の時刻での年齢。「決まっている」の年齢が null でなければその値。"
    f"「登場する話のプロット」があれば、この時刻・この場所でその話の役どころ(作者の指定)を果たせる歳({_SCENE_AGE_RANGE[0]}〜{_SCENE_AGE_RANGE[1]})にする。"
    f"無ければ人物説明と矛盾しない値({_AGE_RANGE[0]}〜{_AGE_RANGE[1]})をあなた自身で決める。例えば老成した説明なら年長めに、幼さの残る説明なら年少めに")
_HISTORY_DESCRIPTION = (
    "来歴。生まれてから年齢の歳(現在の時刻)までの節目を歳の順に、幼ければ0〜2件、大人なら3〜5件。"
    "人物説明の立場・仕事・住まいには、いつそうなったかの節目を必ず含める。現在より後の節目・死は含めない")


class PersonContentDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    text: str = Field(description=(
        "現在の時刻での、具体的な生活・仕事・関係が伝わる2〜3文の人物説明。目立った能力・特技があれば含める。"
        "「優しい」「謎めいた」のような、誰にでも当てはまる抽象的な形容だけで済ませず、"
        "この人物固有の具体的な癖・関わり・生い立ちを最低一つ含める。口調・話し方は tone・dialect に書き、ここには書かない"))
    age: int = Field(ge=0, description=_PERSON_AGE_DESCRIPTION)
    principle: str = Field(description="行動原理(ミーム)どうしの関係を整理した2〜4文。ミームが渡されていなければ空文字")
    personality: PersonalityDraft = Field(description=(
        "性格の各軸(無/低/並/高/必)。行動原理(ミーム)の古今表裏と、出自・生い立ち・年齢・人物説明から総合的に決める"))
    sex: str = Field(description="性別。「男」「女」に限らず、この人物に合う性のあり方を自由に決めてよい")
    height: float = Field(gt=0, description="背丈(cm)。年齢・性別・体格・出自に合う値")
    build: str = Field(description="体格。肉付き・立ち姿など、生活・仕事と行動原理(ミーム)に合う体つきを1文で")
    first_person: str = Field(description="一人称。年齢・性別・性格・出自・話し相手との間柄に合わせる")
    second_person: str = Field(description="二人称。この人物が相手を呼ぶときの言葉")
    third_person: str = Field(description="三人称。この人物が他者に付ける呼び方(敬称)")
    tone: str = Field(description="口調。文体・話し方の癖が伝わるように1文で")
    dialect: str = Field(description=(
        "方言。出身地・参考地域・参考文化・生業・生い立ち・年齢・性格・口調から、この人物がどんな言葉で話すかを1〜2文で。"
        "土地の言葉で話すなら、どの地方風の方言か(現実の方言を手本にしてよい)と、特徴的な語尾・言い回しを一つ以上。"
        "標準語で話すなら、その人物らしい癖(語尾・口ぐせ・言い淀み・訛りの名残など)を一つ以上。"
        "誰にでも当てはまる「普通の話し方」で済ませない"))
    history: list[HistoryItemDraft] = Field(description=_HISTORY_DESCRIPTION)

    @field_validator("age", mode="before")
    @classmethod
    def _age(cls, value: Any) -> Any:
        return _not_negative(value)

    @field_validator("text", "principle", "sex", "build", "first_person", "second_person", "third_person",
                     "tone", "dialect")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()

    @field_validator("text")
    @classmethod
    def _described(cls, value: str) -> str:
        if not value:
            raise ValueError("人物説明が空")
        return value


class NonPersonContentDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    # 候補の外の種別が返ったときは、呼び出し側がサイコロで決め直す
    kind: str = Field(description="種別", json_schema_extra={"enum": list(constants.NON_PERSON_KINDS)})
    text: str = Field(description=(
        "現在の時刻での、この対象が何であって、何を決められて、誰に対して力を持つのかが伝わる2〜3文の説明。"
        "「由緒ある」「謎めいた」のような、どの対象にも当てはまる形容だけで済ませない"))
    age: int = Field(ge=0, description="成り立ってからの年数。「決まっている」の年齢が null でなければその値")
    principle: str = Field(description="行動原理(ミーム)どうしの関係を整理した2〜4文。ミームが渡されていなければ空文字")

    @field_validator("age", mode="before")
    @classmethod
    def _age(cls, value: Any) -> Any:
        return _not_negative(value)

    @field_validator("text", "principle")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()

    @field_validator("text")
    @classmethod
    def _described(cls, value: str) -> str:
        if not value:
            raise ValueError("説明が空")
        return value


class PersonNameDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="名字を含めない名")
    family_name: str = Field(description="名字。その土地・身分で名字を持たないのが自然なら空文字")

    @field_validator("name", "family_name")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def _named(cls, value: str) -> str:
        if not value:
            raise ValueError("名前が空")
        return value


class NameDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="名前")

    @field_validator("name")
    @classmethod
    def _named(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("名前が空")
        return value


class StoryElementsRequest(Material):
    time: Stamp
    stories: list[StoryPlotMaterial]
    later_ideas: list[IdeaMaterial]


class StoryElementsRequestSerialized(StoryElementsRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "現在の時刻": str(self.time),
            "この時刻より後に始まる設定(まだ無い)": [
                {"名前": idea.name, "種類": idea.kind, "始まる年": idea.start.year if idea.start else None}
                for idea in self.later_ideas],
            "筋書き": "\n\n".join(story.text for story in self.stories if story.text),
        }


class BirthSources(Material):
    """人物・対象を生むときに db から読む材料。"""

    born_location: BirthLocationMaterial | None = None
    # 上位の場所のものから順
    stories: list[StoryPlotMaterial]
    # この時刻より後に始まる、まだ世に無い設定
    later_ideas: list[IdeaMaterial]
    nearby_characters: list[NearbyCharacter]
    # 同じ場所(居場所とその上位・配下)にいる人物・対象の名。名付けで避ける
    resident_names: list[str]
    # 引く元になるミーム(`meme.extractor.draw_from`)
    meme_pool: list[PooledMeme]


class CharacterContent(Material):
    """中身(説明・年齢・口調)まで決まった人物・対象。設定を踏まえた清書と名付けはこの後。"""

    material: CharacterBirthMaterial
    content: PersonContentDraft | NonPersonContentDraft
    kind: str
    age: int
    parameters: CharacterParameterValues


class CharacterWriting(Material):
    """生んだ人物・対象の芯と来歴。"""

    # 芯(説明)
    text: str
    # `- <古今表裏>: <文面>` の箇条書き
    meme: str | None = None
    principle: str | None = None
    # 来歴の節目ごとの行(起きた年から始まる)
    histories: list[CharacterHistoryRow]


class CharacterCreation(Material):
    """生んだ人物・対象として足す値。"""

    name: str
    kind: str
    writing: CharacterWriting
    main_character: bool
    parameters: CharacterParameterValues
    birth: Stamp
    # 死亡していなければ空
    end: Stamp | None = None
    born_location_id: int | None = None


class CompletionTarget(Material):
    """芯(text)を埋める人物・対象の、決まっている値。"""

    name: str | None = None
    kind: str
    time: Stamp
    person: bool
    born_location_id: int | None = None
    age: int | None = None
    parameters: CharacterParameterValues | None = None
    # 芯のほかに作者が書いた列(外見・ミーム・行動原理・筋書き)。核として渡す
    hint_text: str | None = None
