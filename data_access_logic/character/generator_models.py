from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from data_access_logic import constants
from data_access_logic.character.models import CharacterBase, CharacterParameterValues
from data_access_logic.idea.models import IdeaContextMaterial, IdeaContextSerialized, IdeaMaterial
from data_access_logic.location.models import LocationMaterial, PlaceMaterial
from data_access_logic.material import Material
from data_access_logic.meme.models import DrawnMeme
from data_access_logic.story.models import StoryPlotMaterial
from db.stamp import Stamp

_AGE_RANGE = constants.GENERATION_CHARACTER_AGE_RANGE


class BirthPlaceMaterial(PlaceMaterial):
    sample_region: str | None = None
    sample_culture: str | None = None
    sample_era: str | None = None
    parent: LocationMaterial | None = None


class CharacterBirthMaterial(Material):
    time: Stamp
    person: bool
    born_place: BirthPlaceMaterial | None = None
    # 上位の場所のものから順
    stories: list[StoryPlotMaterial]
    # この時刻より後に始まる、まだ世に無い設定
    later_ideas: list[IdeaMaterial]
    # 筋書きから抜き出した立場のうち、サイコロで選んだもの
    element: str | None = None
    memes: list[DrawnMeme]
    nearby_characters: list[CharacterBase]
    # 人物なら、サイコロと作者の指定で決まっている値。決まっていない値は None
    parameters: CharacterParameterValues | None = None
    # 以下は決まっている値。None なら AI が決める
    name: str | None = None
    kind: str | None = None
    age: int | None = None
    # 作者が下書きに書いた名前・説明。核にするが言い回しは変えてよい
    hint_name: str | None = None
    hint_text: str | None = None


def _born_place(born_place: BirthPlaceMaterial | None) -> dict[str, Any] | None:
    if born_place is None:
        return None
    return {
        "名前": born_place.name,
        "種別": born_place.kind,
        "説明": born_place.text,
        "参考地域": born_place.sample_region,
        "参考文化": born_place.sample_culture,
        "参考時代": born_place.sample_era,
        "所属する地域": (f"{born_place.parent.name}({born_place.parent.kind})"
                         if born_place.parent else None),
    }


def _personality(parameters: CharacterParameterValues) -> dict[str, str]:
    return {
        "誠実性": parameters.sincerity,
        "好奇心": parameters.curiosity,
        "行動力": parameters.proactivity,
        "協調性": parameters.cooperativeness,
        "社交性": parameters.sociability,
        "感情表現": parameters.emotional_expression,
        "自己肯定感": parameters.self_esteem,
        "自己効力感": parameters.self_efficacy,
        "ストレス耐性": parameters.stress_resilience,
        "価値観の柔軟性": parameters.flexibility_of_values,
        "感受性": parameters.sensitivity,
        "想像力": parameters.imagination,
    }


def _truncated(text: str | None) -> str:
    text = (text or "").strip()
    return text[:constants.IDEA_CONTEXT_LETTERS] + "…" if len(text) > constants.IDEA_CONTEXT_LETTERS else text


class CharacterBirthMaterialSerialized(CharacterBirthMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        parameters = self.parameters
        return {
            "現在の時刻": str(self.time),
            "出身": _born_place(self.born_place),
            "この場所・時刻に関連する筋書き": "\n\n".join(story.text for story in self.stories if story.text) or None,
            "この時刻より後に始まる設定(まだ無い)": [
                {"名前": idea.name, "種類": idea.kind, "始まる年": idea.start.year if idea.start else None,
                 "内容": _truncated(idea.text)}
                for idea in self.later_ideas],
            "体現する要素": self.element,
            "行動原理(ミーム)": [{"古今表裏": meme.position, "内容": meme.text} for meme in self.memes],
            "既にいる人物・対象": [
                {"名前": character.name, "種別": character.kind, "説明": character.text}
                for character in self.nearby_characters],
            "性格": _personality(parameters) if parameters else None,
            "決まっている": {
                "名前": self.name,
                "種別": self.kind,
                "年齢": self.age,
                "性別": parameters.sex if parameters else None,
                "体格": parameters.build if parameters else None,
                "一人称": parameters.first_person if parameters else None,
                "二人称": parameters.second_person if parameters else None,
                "三人称": parameters.third_person if parameters else None,
                "口調": parameters.tone if parameters else None,
            },
            "作者の指定": {"名前": self.hint_name, "説明": self.hint_text},
        }


class CharacterNameMaterial(Material):
    kind: str
    text: str
    age: int
    parameters: CharacterParameterValues | None = None
    born_place: BirthPlaceMaterial | None = None
    nearby_characters: list[CharacterBase]
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
            "体格": parameters.build if parameters else None,
            "一人称": parameters.first_person if parameters else None,
            "二人称": parameters.second_person if parameters else None,
            "三人称": parameters.third_person if parameters else None,
            "口調": parameters.tone if parameters else None,
            "方言": parameters.dialect if parameters else None,
            "居場所": _born_place(self.born_place),
            "既にいる人物・対象の名": [character.name for character in self.nearby_characters],
            "作者が付けたい名": self.hint_name,
        }


def _clamped_age(value: Any) -> Any:
    try:
        return min(max(int(value), _AGE_RANGE[0]), _AGE_RANGE[1])
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

    age: int = Field(ge=0, le=_AGE_RANGE[1], description="その時の歳")
    text: str = Field(description="その歳に何があり、立場・仕事・住まい・人間関係がどう変わったかの1文")


class PersonContentDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    text: str = Field(description=(
        "具体的な生活・仕事・関係が伝わる2〜3文の人物説明。目立った能力・特技があれば地の文として含め、別項目には分けない。"
        "「優しい」「謎めいた」のような、誰にでも当てはまる抽象的な形容だけで済ませず、"
        "この人物固有の具体的な癖・関わり・生い立ちを最低一つ含める"))
    age: int = Field(ge=_AGE_RANGE[0], le=_AGE_RANGE[1], description=(
        "年齢。人物説明と矛盾しない値をあなた自身で決める。例えば老成した説明なら年長めに、幼さの残る説明なら年少めに"))
    principle: str = Field(description="行動原理(ミーム)どうしの関係を整理した2〜4文。ミームが渡されていなければ空文字")
    sex: str = Field(description="性別。「男」「女」に限らず、この人物に合う性のあり方を自由に決めてよい")
    build: str = Field(description="体格。背丈・肉付き・立ち姿など、生活・仕事に合う体つきを1文で")
    first_person: str = Field(description="一人称。年齢・性別・性格・出自・話し相手との間柄に合わせる")
    second_person: str = Field(description="二人称。この人物が相手を呼ぶときの言葉")
    third_person: str = Field(description="三人称。この人物が他者に付ける呼び方(敬称)")
    tone: str = Field(description="口調。文体・話し方の癖が伝わるように1文で")
    dialect: str = Field(description=(
        "方言。出身地・参考地域・参考文化・生業・生い立ち・年齢・性格・口調から、この人物がどんな言葉で話すかを1〜2文で。"
        "土地の言葉で話すなら、どの地方風の方言か(現実の方言を手本にしてよい)と、特徴的な語尾・言い回しを一つ以上。"
        "標準語で話すなら、その人物らしい癖(語尾・口ぐせ・言い淀み・訛りの名残など)を一つ以上。"
        "誰にでも当てはまる「普通の話し方」で済ませない"))
    history: list[HistoryItemDraft] = Field(description=(
        "来歴。生まれてから年齢の歳までの節目を、歳の順に3〜5件。人物説明の立場・仕事・住まいには、いつそうなったかの節目を必ず含める"))

    @field_validator("age", mode="before")
    @classmethod
    def _age(cls, value: Any) -> Any:
        return _clamped_age(value)

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
        "この対象が何であって、何を決められて、誰に対して力を持つのかが伝わる2〜3文の説明。"
        "「由緒ある」「謎めいた」のような、どの対象にも当てはまる形容だけで済ませない"))
    age: int = Field(ge=_AGE_RANGE[0], le=_AGE_RANGE[1], description="成り立ってからの年数")
    principle: str = Field(description="行動原理(ミーム)どうしの関係を整理した2〜4文。ミームが渡されていなければ空文字")

    @field_validator("age", mode="before")
    @classmethod
    def _age(cls, value: Any) -> Any:
        return _clamped_age(value)

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


class PolishDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="清書した説明")

    @field_validator("text")
    @classmethod
    def _described(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("説明が空")
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
                {"名前": idea.name, "種類": idea.kind, "始まる年": idea.start.year if idea.start else None,
                 "内容": _truncated(idea.text)}
                for idea in self.later_ideas],
            "筋書き": "\n\n".join(story.text for story in self.stories if story.text),
        }


class PolishRequest(Material):
    draft: str
    ideas: IdeaContextMaterial


class PolishRequestSerialized(PolishRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {"下書き": self.draft, "関係する設定": IdeaContextSerialized.model_validate(self.ideas).model_dump()}
