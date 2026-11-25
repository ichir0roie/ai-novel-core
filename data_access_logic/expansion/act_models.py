"""人物モード(`SimulateDay`)の材料と、AI の出力の形。

人物の目(一時間ごとの手・居合わせた相手への応じ)には、その人物が知ることのできるデータ(`character/knowledge.py`)と、目の前の様子だけを
渡す。年の数は渡さず、今の時刻は月日・時間帯・時で、思い・出来事のいつは今からの隔たりで渡す(`character/time_sense.py`)。
作者の目(一日の終わりの記録)には、人物の一日の行動と、作者が置いた筋・前後の話のプロット・居合わせた人物の思いを渡す。
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_serializer

from data_access_logic import constants
from data_access_logic.character.knowledge import AppearanceSerialized, KnowledgeSerialized
from data_access_logic.character.record import (
    CharacterMotivationRecord, CharacterMove, GeneratedCharacter, MotivationChange,
)
from data_access_logic.character.time_sense import TimeSense
from data_access_logic.event.models import EventSerialized
from data_access_logic.event.progress_models import CharacterUpdateDraft
from data_access_logic.event.record import EventRecord
from data_access_logic.location.models import LocationMaterial
from data_access_logic.material import Material, Timestamp
from db import story_scope
from db.stamp import Calendar, Stamp, active_calendar
from db.story_scope import Scope


class ImpactFrame(BaseModel):
    """一日が世界を動かせる幅(`expansion/budget.py`)。記録する段に渡し、はみ出た分はコードが切る。"""

    influence: str
    # 来歴に変化を残せる(人となりが分かる)人数。動いた人物を含む
    people: int
    moves: int
    new_characters: int
    ideas: int
    # 動いた人物より影響力が上で、この一日では来歴・居場所を動かされない人物
    resistant_ids: list[int] = []
    resistant_names: list[str] = []

    def for_prompt(self) -> dict[str, Any]:
        return {
            "人となりの変化を残せる人数(動いた人物を含む)": self.people,
            "住まい・拠点を移せる人数": self.moves,
            "新しく現れる人物・対象の数": self.new_characters,
            "生まれる・広まる事柄の数": self.ideas,
            "動かされにくい人物(人となりの変化・住まいの移動を書かない)": self.resistant_names,
        }


class PresentPerson(Material):
    character_id: int
    # 見る人が名を知らなければ、人物の目には名前を伏せて渡す
    name: str | None = None
    looks: AppearanceSerialized


class MotivationLine(Material):
    """その時刻に効いているモチベーションの行。"""

    id: int
    start: Timestamp
    strength: int
    text: str

    def for_prompt(self) -> dict[str, Any]:
        """作者の目(記録する段)に渡す形。いつからを暦の時刻で言う。"""
        return {"モチベーションid": self.id, "強さ": self._strength(), "内容": self.text, "いつから": str(self.start)}

    def for_character(self, sense: TimeSense, now: Stamp) -> dict[str, Any]:
        """人物の目に渡す形。いつからを今からの隔たりで言う。"""
        return {"モチベーションid": self.id, "強さ": self._strength(), "内容": self.text, "いつから": sense.ago(self.start, now)}

    def _strength(self) -> str:
        return f"{self.strength}({constants.MOTIVATION_STRENGTHS.get(self.strength, '')})"


class Motives(Material):
    """人物の目に渡す、本人のモチベーションと前後の出来事。本人の内心なので、本人の材料にだけ入れる。"""

    # 強い順
    motivations: list[MotivationLine]
    # 本人が当事者だった出来事(新しい順)
    past_events: list[EventSerialized]
    # 本人か居る場所に掛かる、この時刻より後に既に決まっている出来事(古い順)。本人はまだ知らない
    later_events: list[EventSerialized]

    def for_prompt(self, sense: TimeSense, now: Stamp) -> dict[str, Any]:
        """人物の目に渡す形。出来事のいつは今からの隔たり(この先の出来事は「5日後」)で言う。"""
        return {
            "あなたのモチベーション(強い順)": [motivation.for_character(sense, now) for motivation in self.motivations],
            "あなたが関わったこれまでの出来事(新しい順)": [_event_for_character(event, sense, now) for event in self.past_events],
            "この先に決まっている出来事(あなたはまだ知らない)": [
                _event_for_character(event, sense, now) for event in self.later_events],
        }


def _event_for_character(event: EventSerialized, sense: TimeSense, now: Stamp) -> dict[str, Any]:
    return {"いつ": sense.ago(event.time, now), "名前": event.name,
            "場所": event.location.name if event.location else None,
            "要約": event.summary.text if event.summary else None}


class ParticipantMotivations(Material):
    """記録する段に渡す、居合わせた人物ごとの、その時刻に効いているモチベーション。"""

    character_id: int
    name: str | None = None
    motivations: list[MotivationLine]


class NarratedEpisode(Material):
    """記録する段が逆らわないように読む話。本文のある話は、プロットと本文のとおりに起きたこととして扱う。"""

    id: int
    title: str
    start: Timestamp
    end: Timestamp | None = None
    plot_text: str
    written: bool


class ArcEvent(Material):
    id: int
    name: str
    time: Timestamp
    end: Timestamp | None = None
    text: str


class ParentArc(BaseModel):
    """作者が置いた親の出来事の筋。記録する段が逆らわないように読む。"""

    # 一番上の先祖から親までの順
    chain: list[ArcEvent]
    # 同じ親の子のうち、その日より前・後に置かれた出来事(時刻の順)
    before: list[ArcEvent] = []
    after: list[ArcEvent] = []

    def for_prompt(self) -> dict[str, Any]:
        def rows(events: list[ArcEvent]) -> list[dict[str, Any]]:
            return [{"名前": event.name, "時刻": str(event.time), "終わり": None if event.end is None else str(event.end),
                     "本文": event.text} for event in events]
        return {"親の出来事と、その上の出来事(大きい順)": rows(self.chain),
                "同じ親の下で、その日より前に置かれた出来事": rows(self.before),
                "同じ親の下で、その日より後に置かれた出来事": rows(self.after)}


class AuthorPlan(BaseModel):
    """作者が置いた筋と、その日の前後に人物が出るプロットつきの話。記録する段に、逆らわないよう渡す。"""

    parent: ParentArc | None = None
    episodes: list[NarratedEpisode] = []

    def for_prompt(self) -> dict[str, Any]:
        return {
            "作者が置いた筋": None if self.parent is None else self.parent.for_prompt(),
            "前後の話(時刻の順)": [
                {"題": episode.title, "時刻": str(episode.start), "終わり": None if episode.end is None else str(episode.end),
                 "本文": "あり" if episode.written else "まだ無い", "プロット": episode.plot_text}
                for episode in self.episodes],
        }


class DayPlace(Material):
    """人物が一日のうちに行ける、エリアの詳細の場所。"""

    id: int
    name: str | None = None
    kind: str | None = None
    # 一つ上の場所の名前(同じ名前の部屋を見分ける)
    parent_name: str | None = None

    def for_prompt(self) -> dict[str, Any]:
        return {"場所id": self.id, "名前": self.name, "種別": self.kind, "どこの": self.parent_name}


class FixedSlot(BaseModel):
    """作者の出来事・話の予定で決まった一時間。人物はその時間、予定の場所で予定のことをしている。"""

    hour: int
    location_id: int
    label: str
    event_id: int | None = None
    episode_id: int | None = None


class Needs(BaseModel):
    """空腹と、人と触れ合いたい欲と眠気(0〜100)。一時間ごとに規則で動かす(`expansion/needs.py`)。"""

    hunger: int
    desire: int
    sleepiness: int = 0

    def for_prompt(self, fatigue: int) -> dict[str, str]:
        words = constants.DAY_NEED_WORDS
        return {"眠気": _need_word(self.sleepiness, words["眠気"]), "空腹": _need_word(self.hunger, words["空腹"]),
                "人恋しさ": _need_word(self.desire, words["人恋しさ"]), "疲れ": _need_word(fatigue, words["疲れ"])}


class NeedProfile(BaseModel):
    """人物のその日の欲の段と、眠りの段取りと、行動量。時刻はその日の一時間の番号(0 が 0 時)で持つ。"""

    appetite: str
    sleep_drive: str
    libido: str
    # 前の日に満ち足りなかったぶん、その日に強く働く割合(1 で前の日と同じ)
    food_pressure: float = 1.0
    touch_pressure: float = 1.0
    # 一晩に要る眠りの時間
    required_sleep: int
    # 前の夜に眠った時刻。0 以下は前の日のうち(-2 なら前の日の 22 時)、正なら日付が変わってから起きていた
    prev_bed: int
    # その朝に起きる時刻と、その夜に眠る時刻(一日の時間の数以上なら、日付が変わってから眠る)
    wake: int
    bed: int
    # その日より前の `DAY_LOOKBACK_DAYS - 1` 日の行動量の和と、七日の上限
    load_before: int = 0
    load_max: int = 0


def _need_word(value: int, words: tuple[tuple[int, str], ...]) -> str:
    return next(word for limit, word in words if value < limit)


class DayCharacter(BaseModel):
    """一日を動かす人物と、その日の始まりの様子。"""

    character_id: int
    name: str | None = None
    # 人物がいるエリア(詳細の場所の一番近い、詳細でない上の場所)
    area_id: int
    # その日の始まりにいた詳細の場所
    home_id: int
    influence: str = "並"
    fixed: list[FixedSlot] = []
    needs: Needs
    profile: NeedProfile
    # さかのぼった不足から決めた、欲(food・sleep・touch)を満たしたいモチベーションの強さ(0 なら持たない)
    need_strengths: dict[str, int] = {}
    # この人物の一日を記録する展開
    expansion_id: int | None = None

    def fixed_at(self, hour: int) -> FixedSlot | None:
        return next((slot for slot in self.fixed if slot.hour == hour), None)


class ActFailure(BaseModel):
    expansion_id: int | None = None
    character_id: int | None = None
    name: str | None = None
    error: str


class DayForm(BaseModel):
    # 動かす人物。空なら、本文のある最新の話の登場人物
    character_ids: list[int] = []
    # 動かす日(人物の暦の日付)。省けば、人物が最後に出た日の翌日
    date: Stamp | None = None
    # 作者が置いた親の出来事。渡せば、一日の出来事をその子にする
    parent_event_id: int | None = None


class DayPlan(BaseModel):
    """一日を動かす段取り。人物ごとの始まりの様子と、エリアごとの行ける場所。"""

    # その日の始まりと、暦の一時間ごとの始まり
    date: Timestamp
    hours: list[Timestamp]
    day_end: Timestamp
    # エリアの id ごとの、行ける詳細の場所
    places: dict[int, list[DayPlace]] = {}
    characters: list[DayCharacter] = []
    failed: list[ActFailure] = []
    parent_event_id: int | None = None


class DayBriefForm(BaseModel):
    character_id: int
    time: Stamp
    seeds: list[str] = []
    nudge: str | None = None


class DaySerialized(Material):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。人物が知ることは整形した形で組むので、db の側で dump して
    `DayBrief.prompt` に入れて運ぶ。一日のあいだ変わらない材料だけを持つ(一時間ごとの様子は `HourScene`)。"""

    time: Timestamp
    knowledge: KnowledgeSerialized
    motives: Motives
    # ほかの場面の筋から時代・場所・固有名詞を抜いたもの。思いつきの元
    seeds: list[str]
    nudge: str | None = None
    # 隔たりを数える暦(組み立てたときの文脈の暦)
    calendar: Calendar | None = Field(default_factory=active_calendar)

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        sense = TimeSense(self.calendar)
        return {
            "あなたが知っていること": self.knowledge.model_dump(),
            **self.motives.for_prompt(sense, self.time),
            "思いつきの元": self.seeds,
            "作者からの方向づけ": self.nudge,
        }


class DayBrief(BaseModel):
    """一日の人物の目の材料(段の出力。web では JSON で運ぶ)。"""

    character_id: int
    name: str | None = None
    prompt: dict[str, Any]
    # この人物が名前を知っている人物
    known_ids: list[int]


class PeopleForm(BaseModel):
    time: Stamp
    # 動かしている人物ごとの、今いる場所
    positions: dict[int, int]


class PlacePeople(BaseModel):
    """一つの場所にいる人物。動かしている人物と、そこに住まいがあり手の空いた、動かしていない人物。"""

    location_id: int
    location_name: str | None = None
    people: list[PresentPerson]


class HourScene(BaseModel):
    """人物の目に渡す、この一時間の目の前の様子。会話の中で前に渡したもの(知っていること・行ける場所)は渡し直さない。"""

    time: Timestamp
    location_id: int
    location_name: str | None = None
    needs: Needs
    # 七日の行動量の、上限に対する割合(百分率)
    fatigue: int
    # 前に聞いてから、人物の目に聞かずに過ぎた時間(眠っていた・予定・休んだ。起きた順)
    meanwhile: list[str]
    present: list[PresentPerson]
    # 目の前の人物が、さっきの一時間にしたこと
    seen: list[str]
    calendar: Calendar | None = Field(default_factory=active_calendar)

    def for_prompt(self, known_ids: list[int], seen_ids: set[int]) -> dict[str, Any]:
        """`seen_ids` は会話の中で見た目を渡した人物。二度目からは見た目を渡さない(会話が覚えている)。"""
        sense = TimeSense(self.calendar)
        return {
            "いま": sense.now_for_prompt(self.time),
            "前に決めてから、過ぎた時間にしていたこと": self.meanwhile,
            "いる場所": {"場所id": self.location_id, "名前": self.location_name},
            "体の具合": self.needs.for_prompt(self.fatigue),
            "目の前にいる人物": [
                {"人物id": person.character_id,
                 "名前": person.name if person.character_id in known_ids and person.name else "(名を知らない)",
                 **({} if person.character_id in seen_ids else person.looks.model_dump())} for person in self.present],
            "目の前の人物が、さっきしていたこと": self.seen,
        }


def _deeds_field() -> Any:
    notes = "・".join(f"{deed}({note})" for deed, note in constants.DAY_DEED_NOTES.items())
    return Field(description=f"この一時間にした行い。{notes} から当てはまるものすべて。無ければ空")


def _known_deeds(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(value.strip() for value in values) if value in constants.DAY_DEED_WEIGHTS]


class HourDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description=f"この一時間にすることの種別。{'・'.join(constants.DAY_ACTION_KINDS)} から一つ")
    location_id: int = Field(description="この一時間を過ごす場所の場所id。行ける場所の中から。動かないなら、いる場所の場所id")
    action: str = Field(description="この一時間にすること。どこで・誰に・何をするか")
    speech: str | None = Field(description="口にする言葉。黙っているなら null")
    thought: str = Field(description="いまの内心")
    deeds: list[str] = _deeds_field()

    @field_validator("deeds")
    @classmethod
    def _deeds(cls, values: list[str]) -> list[str]:
        return _known_deeds(values)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        value = value.strip()
        return value if value in constants.DAY_ACTION_KINDS else "そのほか"

    @field_validator("action")
    @classmethod
    def _filled(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("空")
        return value


class ReactionDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    action: str = Field(description="目の前の人物のしたこと・言ったことを受けて、この一時間のうちにすること。気に留めないなら、そのまま続けること")
    speech: str | None = Field(description="口にする言葉。黙っているなら null")
    thought: str = Field(description="いまの内心")
    deeds: list[str] = _deeds_field()

    @field_validator("deeds")
    @classmethod
    def _deeds(cls, values: list[str]) -> list[str]:
        return _known_deeds(values)


class HourAction(BaseModel):
    """人物の一時間の行動。動かし終えたら行動の表(`event_action`)に一行で足す。"""

    character_id: int
    time: Stamp
    location_id: int
    kind: str
    text: str
    speech: str | None = None
    thought: str | None = None
    sleepiness: int
    hunger: int
    desire: int
    load: int
    fixed_event_id: int | None = None
    fixed_episode_id: int | None = None


class CharacterDayForm(BaseModel):
    """人物の一日の、欲の満ち足り方(0〜100)と行動量。`bedtime` はその夜に眠った時刻(その日の一時間の番号)。"""

    character_id: int
    expansion_id: int
    date: Stamp
    food: int
    sleep: int
    touch: int
    load: int
    bedtime: int


class NeedMotivationForm(BaseModel):
    """さかのぼった不足から決めた、欲を満たしたいモチベーションの強さ(0 なら持たない)。"""

    character_id: int
    time: Stamp
    # 欲(food・sleep・touch)ごとの強さ
    strengths: dict[str, int]


class ActionsForm(BaseModel):
    # 行動を足す人物の一日の展開
    expansion_id: int
    actions: list[HourAction]


class ActIdeaDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(description="この一日で生まれた・広まった事柄(技術・制度・概念・呼称・噂など)の本質の名前")
    kind: str = Field(description="種別。「技術」「制度」「概念」「呼称」「現象」「施設」などの短い語で一つ")
    description: str = Field(description="その事柄の本質。作者だけが読む説明")
    called: str = Field(description="作中でこの場所の人がそれを呼ぶ名前")
    detail: str = Field(description="作中の人がそれについて知っている・信じていること")
    knower_ids: list[int] = Field(description="それを知った人物の人物id。居合わせた人物の中からだけ選ぶ")


class NewCharacterDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(description="この一日で新しく現れる人物・対象の人物像と役どころ(雇った者・作った組織など)")
    person: bool = Field(description="人物なら true、組織・集団・物など人物以外なら false")
    relation: str = Field(description="動いた人物から見た、その人物・対象との間柄の短い名前(雇い人・創った組織など)")


class DayOutcomeDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    event_name: str = Field(description="人物の一日の出来事の名前")
    event_text: str = Field(description="人物の一日の出来事の内容")
    character_ids: list[int] = Field(description="この一日に関わった人物・対象の人物id。居合わせた人物の中からだけ選ぶ。動いた人物も入れる")
    character_moves: list[CharacterMove] = Field(description="住まい・拠点が変わった人物ごとの移動先。誰も変わっていなければ空")
    character_updates: list[CharacterUpdateDraft] = Field(description="この一日を通して人となりについて新しく分かった人物・対象")
    ideas: list[ActIdeaDraft] = Field(
        description=f"この一日で生まれた・広まった事柄。無ければ空。{constants.ACT_NEW_IDEA_LIMIT}件まで")
    new_characters: list[NewCharacterDraft] = Field(
        description=f"この一日で新しく現れる人物・対象。無ければ空。{constants.ACT_NEW_CHARACTER_LIMIT}件まで")
    motivation_changes: list[MotivationChange] = Field(
        description=f"この一日で生まれた・強さが変わった・果たした・消えたモチベーション。変わらなければ空。"
        f"{constants.ACT_MOTIVATION_CHANGE_LIMIT}件まで")

    @field_validator("event_name")
    @classmethod
    def _named(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("出来事の名前が空")
        return value


class DayMaterialForm(BaseModel):
    actor_id: int
    # 居合わせた人物(動いた人物は含めない)
    participant_ids: list[int]
    date: Stamp
    day_end: Stamp
    home_id: int
    parent_event_id: int | None = None


class DayMaterial(BaseModel):
    """記録する段の、db から読む材料(段の出力)。"""

    frame: ImpactFrame
    motivations: list[ParticipantMotivations]
    destinations: list[LocationMaterial]
    plan: AuthorPlan


class DayRequest(Material):
    actor_name: str | None = None
    # その日の行動(起きた順)。居合わせた相手とのやり取りを含む
    log: list[str]
    # 居合わせた人物(人物id と名前)
    present: dict[int, str | None]
    material: DayMaterial

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        material = self.material
        return {
            **material.plan.for_prompt(),
            "動いた人物": self.actor_name,
            "その日の行動(起きた順)": self.log,
            "居合わせた人物": [{"人物id": id_, "名前": name} for id_, name in self.present.items()],
            "居合わせた人物のモチベーション": [
                {"人物id": person.character_id, "名前": person.name,
                 "モチベーション(強い順)": [motivation.for_prompt() for motivation in person.motivations]}
                for person in material.motivations],
            "移動先の候補": [{"場所id": destination.id, "名前": destination.name, "種別": destination.kind}
                        for destination in material.destinations],
            "影響の枠": material.frame.for_prompt(),
        }


class DaySaveForm(BaseModel):
    actor_id: int
    time: Stamp
    end: Stamp
    location_id: int
    participant_ids: list[int]
    destinations: list[LocationMaterial]
    outcome: DayOutcomeDraft
    parent_event_id: int | None = None


class DaySaved(BaseModel):
    event: EventRecord
    idea_ids: list[int] = []
    moves: list[CharacterMove] = []
    # 一日で足したモチベーションの行(生まれた思いと、強さの変わった思いの新しい行)
    motivations: list[CharacterMotivationRecord] = []


class MotivesForm(BaseModel):
    character_ids: list[int]
    time: Stamp


class NewCharacterLink(BaseModel):
    actor_id: int
    character_id: int
    event_id: int
    relation: str
    time: Stamp


class DayActed(BaseModel):
    expansion_id: int
    character_id: int
    name: str | None = None
    event: EventRecord
    # その日に足した行動の行の数
    actions: int
    idea_ids: list[int] = []
    characters: list[GeneratedCharacter] = []
    moves: list[CharacterMove] = []
    motivations: list[CharacterMotivationRecord] = []
    # 居合わせて互いに動いた相手
    met_ids: list[int] = []
    frame: ImpactFrame | None = None


class DayRun(BaseModel):
    """一回の実行(`SimulateDay`)で動かした一日。"""

    date: Timestamp | None = None
    acted: list[DayActed] = []
    failed: list[ActFailure] = []
    _scope: Scope = PrivateAttr(default_factory=Scope)

    def keep_scope(self, scope: Scope) -> None:
        self._scope = scope

    def dumped(self) -> dict[str, Any]:
        """その日の暦で書き出す。"""
        with story_scope.scoped(self._scope):
            return self.model_dump(mode="json")
