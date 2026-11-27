"""人物モード(`SimulateDay`)の材料と、AI の出力の形。

人物の目(一時間ごとの手・居合わせた相手への応じ)には、その人物が知ることのできるデータ(`character/knowledge.py`)と、目の前の様子だけを
渡す。年の数は渡さず、今の時刻は月日・時間帯・時で、思い・出来事のいつは今からの隔たりで渡す(`character/time_sense.py`)。
作者の目(一日の終わりの記録)には、人物の一日の行動と、作者が置いた筋・前後の話のプロット・居合わせた人物の思いを渡す。
"""
from contextlib import AbstractContextManager
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_serializer

from data_access_logic import constants
from data_access_logic.character.knowledge import AppearanceSerialized, KnowledgeSerialized
from data_access_logic.character.models import NuanceLine
from data_access_logic.character.record import (
    CharacterMotivationRecord, CharacterMove, GeneratedCharacter, MotivationChange,
)
from data_access_logic.character.time_sense import TimeSense
from data_access_logic.event.models import EventSerialized
from data_access_logic.event.progress_models import NuanceChangeDraft
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
    # 一緒に一日を動かしている人物か(動かしていない人物は、決まった居場所から動かない)
    simulated: bool = False
    # その日を先に動かした人物の、この一時間にしていること(行動の表の行い)。先に動かした人物でなければ None
    doing: str | None = None
    # 動かしていない人物が、決まった居場所でしていること(`character_routine.text`)
    routine: str | None = None


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
    """記録する段に渡す、居合わせた人物ごとの、その時刻に効いているモチベーション・癖と思い込みと、動いた人物との間柄。"""

    character_id: int
    name: str | None = None
    motivations: list[MotivationLine]
    nuances: list[NuanceLine] = []
    # 動いた人物との関係の名前(動いた人物本人と、関係の無い人物は空)
    relations: list[str] = []


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


class KnownPeopleForm(BaseModel):
    # 見る人物と、その人物が初めて目の前にした、名前を知っている人物
    viewer_id: int
    character_ids: list[int]
    time: Stamp


class KnownPeople(BaseModel):
    """見る人物が知っている、目の前の人物の外見・芯・来歴(段の出力。整形した形で運ぶ)。"""

    prompt: dict[str, Any]


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
    # 組の中で先に動いた人物が、この一時間にしていること
    now: list[str] = []
    # その日の段取りで床に就く時刻までの時間(暦の一時間で数える)
    until_bed: int
    calendar: Calendar | None = Field(default_factory=active_calendar)

    def for_prompt(self, known_ids: list[int], seen_ids: set[int]) -> dict[str, Any]:
        """`seen_ids` は会話の中で見た目を渡した人物。二度目からは見た目を渡さない(会話が覚えている)。"""
        sense = TimeSense(self.calendar)
        now = sense.now_for_prompt(self.time)
        hours_per_day = 24 if self.calendar is None else self.calendar.hours_per_day
        if hours_per_day != 24:
            # 一日の長さが違う暦では、時の数を 24 時間の感覚で読んで、夕方のうちに寝てしまう
            now["24時間の一日に直すと"] = f"{round(self.time.digits[3] * 24 / hours_per_day)}時ごろ"
        return {
            "いま": now,
            "床に就く目安まで": f"あと{self.until_bed}時間" if self.until_bed > 0 else "もう床に就く時刻",
            "前に決めてから、過ぎた時間にしていたこと": self.meanwhile,
            "いる場所": {"場所id": self.location_id, "名前": self.location_name},
            "体の具合": self.needs.for_prompt(self.fatigue),
            "目の前にいる人物": [
                {"人物id": person.character_id,
                 "名前": person.name if person.character_id in known_ids and person.name else "(名を知らない)",
                 **_day_of(person),
                 **({} if person.character_id in seen_ids else person.looks.model_dump())} for person in self.present],
            "目の前の人物が、さっきしていたこと": self.seen,
            "目の前の人物が、この一時間にしていること": self.now,
        }


def _day_of(person: PresentPerson) -> dict[str, str]:
    if person.simulated:
        return {}
    if person.doing is not None:
        return {"この一日": _RECORDED, "この一時間にしていること": person.doing}
    return {"この一日": _STAYING, **({"ここでしていること": person.routine} if person.routine else {})}


def _deeds_field() -> Any:
    notes = "・".join(f"{deed}({note})" for deed, note in constants.DAY_DEED_NOTES.items())
    return Field(description=f"この一時間にした行い。{notes} から当てはまるものすべて。無ければ空")


def _known_deeds(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(value.strip() for value in values) if value in constants.DAY_DEED_WEIGHTS]


# 動かしていない人物は決まった居場所から動かないので、人物の目に、連れ出せないことを伝える
_STAYING = "ここで過ごしていて、ほかの場所へは一緒に行かない"
# その日を先に動かした人物は、行動の表のとおりに動き、後から動く人物に合わせては変わらない
_RECORDED = "この一日はもう決まっていて、あなたに合わせては変わらない"


def _ate_field() -> Any:
    return Field(description=(
        f"この一時間に食べた量。{'・'.join(constants.DAY_MEAL_AMOUNTS)} から一つ。種別が「食べる」でなくても、"
        "話しながら料理をつまんだ・用事の前に朝ごはんを軽く食べたなら、その量にする"))


def _known_amount(value: str | None) -> str:
    value = (value or "").strip()
    return value if value in constants.DAY_MEAL_AMOUNTS else constants.DAY_MEAL_AMOUNTS[0]


# 台詞は話の本文を書くとき(人物役)に任せ、一時間の手は行いの粒で残す
_ACTION_WORDING = "誰に何を話した・頼んだかは、台詞(かぎかっこ)でなく行いとして書く(「ミレアに都の話の続きをねだる」)"
_ACTION_NOTE = (f"いまいる場所で、これからすること。誰に・何をするか。{_ACTION_WORDING}。"
                "ほかの場所ですること(詰所へ行って働く・市場で買う)なら、この一時間は種別を「移動」にしてそこへ向かうことだけを書き、"
                "着いてからすることは次の一時間に決める")
_NEXT_PLACE_NOTE = ("このことを終えたあとに過ごす場所の場所id。行ける場所の中から。終わりの一時間のうちに歩いて移る。"
                    "ここに残るなら、いる場所の場所id")

_HOURS_NOTE = (f"このことを続ける時間(一時間で数える)。1〜{constants.DAY_BLOCK_MAX_HOURS}。"
               f"{'・'.join(constants.DAY_KIND_HOURS)}は1。中身に合う長さにする(礼を言う・頼むだけなら1、仕事・待つ・稽古なら長く)")
_AFTER_NOTE = ("二時間目から続けること。目の前の人物への働きかけ(話す・頼む・渡す・礼を言う)は最初の一時間で済んだものとし、"
               "ここには自分の手元のことだけを書く(「荷を運び続ける」「石に座って待ち続ける」)。一時間で終えるなら空")

_KIND_NOTE = ("この一時間に何かを食べたなら(つまむ程度でも)「食べる」、親しい相手と寄り添った・手を取ったなら「触れ合う」にする")


class HourDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description=f"この一時間にすることの種別。{'・'.join(constants.DAY_ACTION_KINDS)} から一つ。{_KIND_NOTE}")
    action: str = Field(description=_ACTION_NOTE)
    toward_ids: list[int] = Field(description=(
        "この一時間に働きかける(話しかける・頼む・手を貸す・誘うなど)目の前の人物の人物id。目の前にいる人物の中から。いなければ空"))
    thought: str = Field(description="いまの内心")
    deeds: list[str] = _deeds_field()
    ate: str = _ate_field()
    next_location_id: int = Field(description=_NEXT_PLACE_NOTE)
    hours: int = Field(description=_HOURS_NOTE)
    after_action: str = Field(description=_AFTER_NOTE)

    @field_validator("after_action")
    @classmethod
    def _after(cls, value: str) -> str:
        return value.strip()

    @field_validator("deeds")
    @classmethod
    def _deeds(cls, values: list[str]) -> list[str]:
        return _known_deeds(values)

    @field_validator("ate")
    @classmethod
    def _ate(cls, value: str | None) -> str:
        return _known_amount(value)

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


# 動かしていない人物が決まった居場所にいないとき(住まいにいる時間)の、していること
_AT_HOME = "住まいで過ごしている"
# 応じる人物は決まった居場所から動かないので、ついて行く応じ方をさせない
_STAYING_TODAY = "今日はここで過ごしていて、ほかの場所へは行かない"


class ResponseScene(BaseModel):
    """動かしていない人物の目に渡す、働きかけてきた人物とそのしたこと。"""

    time: Timestamp
    location_name: str | None = None
    # 決まった居場所でしていること(`character_routine.text`)。住まいにいれば None
    routine: str | None = None
    partner: PresentPerson
    # 働きかけてきた人物の名前を知っているか
    partner_known: bool
    # 会話の中で、働きかけてきた人物の見た目を前に渡したか
    partner_seen: bool
    deed: str
    calendar: Calendar | None = Field(default_factory=active_calendar)

    def for_prompt(self) -> dict[str, Any]:
        sense = TimeSense(self.calendar)
        now = sense.now_for_prompt(self.time)
        hours_per_day = 24 if self.calendar is None else self.calendar.hours_per_day
        if hours_per_day != 24:
            now["24時間の一日に直すと"] = f"{round(self.time.digits[3] * 24 / hours_per_day)}時ごろ"
        partner = self.partner
        return {
            "いま": now,
            "いる場所": self.location_name,
            "ここでしていること": self.routine or _AT_HOME,
            "この一日": _STAYING_TODAY,
            "働きかけてきた人物": {
                "人物id": partner.character_id,
                "名前": partner.name if self.partner_known and partner.name else "(名を知らない)",
                **({} if self.partner_seen else partner.looks.model_dump()),
                "あなたにしたこと": self.deed,
            },
        }


class ResponseDraft(BaseModel):
    """動かしていない人物が、働きかけてきた人物にその場で応じること。"""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(description=(
        f"働きかけに、その場でどう応じるか。{_ACTION_WORDING}。取り合わないなら、取り合わずにしていたこと"))
    thought: str = Field(description="いまの内心")

    @field_validator("action")
    @classmethod
    def _filled(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("空")
        return value


class HourAction(BaseModel):
    """人物の一時間の行動。動かし終えたら行動の表(`event_action`)に一行で足す。"""

    character_id: int
    time: Stamp
    location_id: int
    kind: str
    text: str
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
    nuance_changes: list[NuanceChangeDraft] = Field(
        description="この一日で新しく見えた・変わった、人物・対象の癖と思い込み。無ければ空")
    ideas: list[ActIdeaDraft] = Field(
        description=f"この一日で生まれた・広まった事柄。無ければ空。{constants.ACT_NEW_IDEA_LIMIT}件まで")
    new_characters: list[NewCharacterDraft] = Field(
        description=f"この一日で新しく現れる人物・対象。無ければ空。{constants.ACT_NEW_CHARACTER_LIMIT}件まで")
    motivation_changes: list[MotivationChange] = Field(
        description=f"この一日で生まれた・強さが変わった・果たした・消えたモチベーション。変わらなければ空。"
        f"{constants.ACT_MOTIVATION_CHANGE_LIMIT}件まで")
    continues_event_id: int | None = Field(
        default=None, description="その日が「続いている記録」のどれかと同じ暮らしの繰り返しなら、その記録の出来事id。"
        "新しい記録を立てるなら null")

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


class ContinuingEvent(Material):
    """動いた人物の、前の日まで続いている AI の出来事。その日が同じ暮らしの繰り返しなら、この出来事を延ばす。"""

    id: int
    name: str
    time: Timestamp
    end: Timestamp | None = None
    text: str


class DayMaterial(BaseModel):
    """記録する段の、db から読む材料(段の出力)。"""

    frame: ImpactFrame
    motivations: list[ParticipantMotivations]
    destinations: list[LocationMaterial]
    plan: AuthorPlan
    # 動いた人物が当事者の、その日より前の出来事の名前(新しい順)
    recent_names: list[str] = []
    # 動いた人物の、前の日まで続いている AI の出来事(新しい順)
    continuing: list[ContinuingEvent] = []


class DayRequest(Material):
    actor_name: str | None = None
    # その日の行動(起きた順)。居合わせた相手とのやり取りを含む
    log: list[str]
    # 居合わせた人物(人物id と名前)
    present: dict[int, str | None]
    # 居合わせた人物ごとの、居合わせた場所(行動の「母さま」「日焼けした女」を、どの人物か見分けさせる)
    met_places: dict[int, list[str]] = {}
    material: DayMaterial
    # 動いた日の 0 時(前後の話の時刻と比べて、どれがその日の外かを見分けさせる)
    date: Timestamp

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        material = self.material
        relations = {person.character_id: "・".join(person.relations) for person in material.motivations}
        return {
            **material.plan.for_prompt(),
            "その日": str(self.date).split(" ")[0],
            "動いた人物": self.actor_name,
            "動いた人物のこれまでの記録の名前(新しい順)": material.recent_names,
            "続いている記録": [{"出来事id": event.id, "名前": event.name, "始まり": str(event.time), "本文": event.text}
                         for event in material.continuing],
            "その日の行動(起きた順)": self.log,
            "居合わせた人物": [
                {"人物id": id_, "名前": name, "動いた人物との間柄": relations.get(id_) or None,
                 "居合わせた場所": self.met_places.get(id_) or None} for id_, name in self.present.items()],
            "居合わせた人物のモチベーション": [
                {"人物id": person.character_id, "名前": person.name,
                 "モチベーション(強い順)": [motivation.for_prompt() for motivation in person.motivations]}
                for person in material.motivations],
            "居合わせた人物の癖と思い込み": [
                {"人物id": person.character_id, "名前": person.name,
                 "癖と思い込み": [nuance.for_prompt() for nuance in person.nuances]}
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
    # 一日で現れる人物の生まれの場所(記録の場所が居合わせた人物の住まいなら、その一つ上の場所)
    newcomer_location_id: int


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
    # 次の日の 0 時(その日の暦で数える)
    day_end: Timestamp | None = None
    acted: list[DayActed] = []
    failed: list[ActFailure] = []
    _scope: Scope = PrivateAttr(default_factory=Scope)

    def keep_scope(self, scope: Scope) -> None:
        self._scope = scope

    def scoped(self) -> AbstractContextManager[Scope]:
        """動かした人物の暦を立てる(その日の時刻を、その暦で読む・書く)。"""
        return story_scope.scoped(self._scope)

    def dumped(self) -> dict[str, Any]:
        """その日の暦で書き出す。"""
        with self.scoped():
            return self.model_dump(mode="json")

