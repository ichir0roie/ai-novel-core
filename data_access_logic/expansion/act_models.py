"""人物モード(`ActCharacter`)の材料と、AI の出力の形。

人物の目(狙う段)には、その人物が知ることのできるデータ(`character/knowledge.py`)と、目の前の様子だけを渡す。
語り部(狙う段の前)には、一手の前後の話のプロットを渡し、プロットに逆らわないための動機と、人物の目の前で起こす状況を決めさせる。
作者の目(裁く段)には、場所の状況(出来事の生成と同じ `LocationSituationSerialized`)と、人物の狙いと、語り部の動機を渡す。
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from data_access_logic import constants
from data_access_logic.character.knowledge import AppearanceSerialized, KnowledgeSerialized
from data_access_logic.character.record import CharacterMove, GeneratedCharacter
from data_access_logic.event.progress_models import (
    EventRecordDraft, LocationSituationMaterial, LocationSituationSerialized,
)
from data_access_logic.event.record import EventRecord
from data_access_logic.location.models import LocationMaterial
from data_access_logic.material import Material, Timestamp
from db.stamp import Stamp


class ActorPick(BaseModel):
    """動く人物と、動く時刻・場所。気力・影響力は、その時刻の値(`expansion/budget.py`)。"""

    character_id: int
    name: str | None = None
    time: Timestamp
    location_id: int
    energy: float = 0
    influence: str = "並"


class ImpactFrame(BaseModel):
    """一手が世界を動かせる幅(`expansion/budget.py`)。裁く段に渡し、裁いた結果がはみ出た分はコードが切る。"""

    influence: str
    # 来歴に変化を残せる(人となりが分かる)人数。動いた人物を含む
    people: int
    moves: int
    new_characters: int
    ideas: int
    location_change: bool
    # 動いた人物より影響力が上で、この一手では来歴・居場所を動かされない人物
    resistant_ids: list[int] = []
    resistant_names: list[str] = []

    def for_prompt(self) -> dict[str, Any]:
        return {
            "人となりの変化を残せる人数(動いた人物を含む)": self.people,
            "住まい・拠点を移せる人数": self.moves,
            "新しく現れる人物・対象の数": self.new_characters,
            "生まれる・広まる事柄の数": self.ideas,
            "場所をなくす・新しく作る": "できる" if self.location_change else "できない",
            "動かされにくい人物(人となりの変化・住まいの移動を書かない)": self.resistant_names,
        }


class PresentPerson(Material):
    character_id: int
    # 知り合いでなければ名前は分からない
    name: str | None = None
    looks: AppearanceSerialized


class OpenArc(Material):
    """人物がまだ追っている筋(終わりの空いた、親の出来事)。"""

    id: int
    name: str
    text: str


class NarratedEpisode(Material):
    """語り部が動機にする話。本文のある話は、プロットと本文のとおりに起きたこととして扱う。"""

    id: int
    title: str
    start: Timestamp
    end: Timestamp | None = None
    plot_text: str
    written: bool


def _episodes_for_prompt(episodes: list[NarratedEpisode]) -> list[dict[str, Any]]:
    return [{"題": episode.title, "時刻": str(episode.start), "終わり": None if episode.end is None else str(episode.end),
             "本文": "あり" if episode.written else "まだ無い", "プロット": episode.plot_text} for episode in episodes]


class NarratorSerialized(Material):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。語り部は作者の側なので、居合わせる人物を名前で読む。
    人物の来歴・筋書きは渡さない(人物の外のことだけを動かす)。"""

    time: Timestamp
    location_name: str | None = None
    actor_name: str | None = None
    present_names: list[str]
    recent_events: list[str]
    arcs: list[OpenArc]
    episodes: list[NarratedEpisode]
    nudge: str | None = None

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "一手の時刻": str(self.time),
            "場所": self.location_name,
            "動く人物": self.actor_name,
            "居合わせる人物": self.present_names,
            "この場所で近ごろ起きたこと(新しい順)": self.recent_events,
            "動く人物が追っている企て": [{"名前": arc.name, "狙い": arc.text} for arc in self.arcs],
            "前後の話(時刻の順)": _episodes_for_prompt(self.episodes),
            "作者からの方向づけ": self.nudge,
        }


class NarratorBrief(BaseModel):
    """語り部の材料(段の出力)。関わる話が無ければ `episodes` は空で、語り部は呼ばない。"""

    prompt: dict[str, Any]
    episodes: list[NarratedEpisode]


class NarrationDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    motivation: str = Field(
        description="語り部の動機。前後の話のプロットに逆らわないために、この一手のあいだに起きてほしいこと・起きてはならないこと。"
                    "人物には渡らず、一手を裁く作者だけが読む")
    narration: str | None = Field(
        description="動く人物の目の前で起こすこと(人の出入り・用事・知らせ・天気・道・物の在り処)。人物が見聞きできることだけを三人称で。"
                    "起こさないなら null")
    request: str | None = Field(
        description="動く人物に求めること。プロットにあるその人物の行動・台詞のうち、この時刻にすることだけ。無ければ null")


class Narration(BaseModel):
    """語り部が一手に添えたもの。語り部の答えが得られなければ、動機は空のまま前後の話のプロットだけを裁く段に渡す。"""

    episodes: list[NarratedEpisode]
    motivation: str | None = None
    narration: str | None = None
    request: str | None = None

    def as_text(self) -> str:
        episodes = "・".join(f"ep{episode.id}「{episode.title}」" for episode in self.episodes)
        lines = [f"語り部の動機({episodes}): {self.motivation or '(得られなかった。プロットだけを裁く段に渡した)'}"]
        if self.narration:
            lines.append(f"語り部の語り: {self.narration}")
        if self.request:
            lines.append(f"語り部の要求: {self.request}")
        return "\n".join(lines)


class ActorSerialized(Material):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。人物が知ることは整形した形で組むので、db の側で dump して
    `ActorBrief.prompt` に入れて運ぶ。"""

    time: Timestamp
    location_name: str | None = None
    knowledge: KnowledgeSerialized
    present: list[PresentPerson]
    # この場所の直近の出来事の名前(新しい順)
    recent_events: list[str]
    arcs: list[OpenArc]
    # ほかの場面の筋から時代・場所・固有名詞を抜いたもの。思いつきの元
    seeds: list[str]
    # 作者からの軽い方向づけ
    nudge: str | None = None
    # 語り部が目の前で起こしたことと、求めること(プロットは渡さない)
    narration: str | None = None
    request: str | None = None

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "いまの時刻": str(self.time),
            "いる場所": self.location_name,
            "あなたが知っていること": self.knowledge.model_dump(),
            "目の前にいる人物": [
                {"人物id": person.character_id, "名前": person.name or "(名を知らない)", **person.looks.model_dump()}
                for person in self.present],
            "この場所で近ごろ起きたこと(新しい順)": self.recent_events,
            "あなたが追っている企て": [{"企てid": arc.id, "名前": arc.name, "狙い": arc.text} for arc in self.arcs],
            "思いつきの元": self.seeds,
            "作者からの方向づけ": self.nudge,
            "語り部の語り(いま目の前で起きたこと)": self.narration,
            "語り部の要求": self.request,
        }


class ActorBrief(BaseModel):
    """狙う段の材料(段の出力。web では JSON で運ぶ)。"""

    # 人物の目で整形した材料(`ActorSerialized` を dump したもの)
    prompt: dict[str, Any]
    # 居合わせる人物(動く人物は含まない)
    present_ids: list[int]
    arcs: list[OpenArc]


class InviteDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="直に話しかけて巻きこみたい相手の人物id。目の前にいて名前を知っている人物からだけ選ぶ")
    reason: str = Field(description="その相手を巻きこみたいわけ")


class IntentDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    inner: str = Field(description="いまの内心。何を感じ、何を考えているか")
    aim: str = Field(description="この一手で果たしたいこと(狙い)")
    action: str = Field(description="実際にすること。誰に・どこで・何をするか")
    speech: str | None = Field(description="口にする言葉。黙って動くなら null")
    arc_id: int | None = Field(description="追っている企てを続ける一手なら、その企てid。続けないなら null")
    new_arc_name: str | None = Field(
        description="この一手が、何度も手を重ねて果たす新しい企ての始まりなら、その企ての短い名前。そうでなければ null")
    invites: list[InviteDraft] = Field(
        default_factory=list,
        description=f"この一手で直に話しかけ、返事を聞きたい相手。一人で済む一手なら空。{constants.ACT_INVITE_LIMIT}人まで")

    @field_validator("aim", "action")
    @classmethod
    def _filled(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("空")
        return value

    def as_text(self) -> str:
        lines = [f"狙い: {self.aim}", f"行動: {self.action}"]
        if self.speech:
            lines.append(f"言葉: 「{self.speech}」")
        return "\n".join(lines)


class DialogueBrief(BaseModel):
    """巻きこまれた人物・動いた人物が対話の手番を打つ材料(段の出力)。人物役と同じく、その時刻に知ることのできるデータと目の前の様子だけ。"""

    character_id: int
    name: str | None = None
    # 人物の目で整形した材料(知っていること・目の前にいる人物)
    prompt: dict[str, Any]
    # この人物が名前を知っている人物。見聞きしたことの名前は、ここにいる人物だけ名前で書く
    known_ids: list[int]


class DialogueBriefForm(BaseModel):
    character_id: int
    time: Stamp
    location_id: int
    # 対話に加わる人物(本人を含めてよい)。居合わせる人物の頭に必ず入れる
    participant_ids: list[int]
    # 対話に出た文。知っているアイデアは、ここに名前の出るものだけを渡す
    mentioned: str
    # 語り部が目の前で起こしたこと。居合わせる皆に見える
    narration: str | None = None


class DialogueSerialized(Material):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    time: Timestamp
    location_name: str | None = None
    knowledge: KnowledgeSerialized
    present: list[PresentPerson]
    narration: str | None = None

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            "いまの時刻": str(self.time),
            "いる場所": self.location_name,
            "あなたが知っていること": self.knowledge.model_dump(),
            "目の前にいる人物": [
                {"名前": person.name or "(名を知らない)", **person.looks.model_dump()} for person in self.present],
            "語り部の語り(いま目の前で起きたこと)": self.narration,
        }


class InviteForm(BaseModel):
    actor_id: int
    time: Stamp
    location_id: int
    candidate_ids: list[int]
    # この実行でもう動いた・巻きこまれた人物(同じ実行の中では、まだ記録に無いので気力で数えられない)
    exclude_ids: list[int] = []


class DialogueTurnDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    thought: str = Field(description="内心。本人にしか見えない")
    action: str = Field(description="行動。動きの行き先と的を書く。黙って見ているだけなら「黙って見ている」")
    speech: str | None = Field(description="口にする言葉。黙っているなら null")
    aim: str = Field(description="この手番の狙いを一文で")
    done: bool = Field(description="この手番でこの場の話を終える(立ち去る・断る・狙いを果たした・あきらめた)なら true")


class DialogueTurn(BaseModel):
    character_id: int
    name: str | None = None
    thought: str
    action: str
    speech: str | None = None
    aim: str
    done: bool = False

    def seen_by(self, viewer_id: int, known_ids: list[int]) -> str:
        """見聞きした人に見える形。名前を知らない相手は名前を出さない。"""
        if self.character_id == viewer_id:
            who = "あなた"
        else:
            who = self.name if self.character_id in known_ids and self.name else "名を知らない人"
        return f"{who}: {self.action}" + (f"「{self.speech}」" if self.speech else "")

    def as_text(self) -> str:
        return f"{self.name}: {self.action}" + (f"「{self.speech}」" if self.speech else "") + f"(狙い: {self.aim})"


class ActIdeaDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(description="この一手で生まれた・広まった事柄(技術・制度・概念・呼称・噂など)の本質の名前")
    kind: str = Field(description="種別。「技術」「制度」「概念」「呼称」「現象」「施設」などの短い語で一つ")
    description: str = Field(description="その事柄の本質。作者だけが読む説明")
    called: str = Field(description="作中でこの場所の人がそれを呼ぶ名前")
    detail: str = Field(description="作中の人がそれについて知っている・信じていること")
    knower_ids: list[int] = Field(description="それを知った人物の人物id。居合わせる人物・対象の中からだけ選ぶ")


class NewCharacterDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(description="この一手で新しく現れる人物・対象の人物像と役どころ(生まれた子・雇った者・作った組織など)")
    person: bool = Field(description="人物なら true、組織・集団・物など人物以外なら false")
    relation: str = Field(description="動いた人物から見た、その人物・対象との間柄の短い名前(子・雇い人・創った組織など)")


class ActOutcomeDraft(EventRecordDraft):
    ideas: list[ActIdeaDraft] = Field(
        description=f"この一手で生まれた・広まった事柄。無ければ空。{constants.ACT_NEW_IDEA_LIMIT}件まで")
    new_characters: list[NewCharacterDraft] = Field(
        description=f"この一手で新しく現れる人物・対象。無ければ空。{constants.ACT_NEW_CHARACTER_LIMIT}件まで")
    arc_closed: bool = Field(description="続けた企てが、この一手で果たされたか潰えたか")


class BatchOutcomeItem(ActOutcomeDraft):
    act_number: int = Field(description="どの手の記録か。渡した手の番号")

    def outcome(self) -> ActOutcomeDraft:
        return ActOutcomeDraft.model_validate(self.model_dump(exclude={"act_number"}))


class BatchOutcomeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcomes: list[BatchOutcomeItem] = Field(description="渡した手ごとに一件ずつ、手の番号の順に")


class OutcomeRequest(Material):
    situation: LocationSituationMaterial
    destinations: list[LocationMaterial]
    actor_name: str | None = None
    intent: IntentDraft
    roll: str
    arc: OpenArc | None = None
    # 巻きこんだ相手との対話(動いた人物の最初の一手のあとの手番)
    dialogue: list[DialogueTurn] = []
    frame: ImpactFrame
    narration: Narration | None = None


class OutcomeRequestSerialized(OutcomeRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    situation: LocationSituationSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        narration = self.narration
        return {
            "語り部の動機": None if narration is None else {
                "前後の話(時刻の順)": _episodes_for_prompt(narration.episodes),
                "動機": narration.motivation,
                "人物の目の前で起こしたこと": narration.narration,
                "人物に求めたこと": narration.request,
            },
            "場所の状況": self.situation.model_dump(),
            "移動先の候補": [{"場所id": destination.id, "名前": destination.name, "種別": destination.kind}
                        for destination in self.destinations],
            "動いた人物": self.actor_name,
            "人物の内心": self.intent.inner,
            "人物の狙いと行動": self.intent.as_text(),
            "続けた企て": None if self.arc is None else {"名前": self.arc.name, "狙い": self.arc.text},
            "巻きこんだ相手とのやり取り(起きた順)": [turn.as_text() for turn in self.dialogue],
            "サイコロで決まった成り行き": self.roll,
            "影響の枠": self.frame.for_prompt(),
        }


class ActPlan(BaseModel):
    """裁く前の一手。実行の中で手ごとに組み、裁く段にまとめて渡す。"""

    expansion_id: int
    pick: ActorPick
    intent: IntentDraft
    present_ids: list[int]
    invited_ids: list[int] = []
    request: OutcomeRequest


class ActFrameForm(BaseModel):
    actor_id: int
    participant_ids: list[int]
    time: Stamp
    roll: str


class ActSaveForm(BaseModel):
    actor_id: int
    time: Stamp
    location_id: int
    participant_ids: list[int]
    destinations: list[LocationMaterial]
    intent: IntentDraft
    outcome: ActOutcomeDraft


class ActSaved(BaseModel):
    event: EventRecord
    # 一手が続けた・始めた企て(親の出来事)。無ければ None
    arc_id: int | None = None
    idea_ids: list[int] = []
    moves: list[CharacterMove] = []


class NewCharacterLink(BaseModel):
    actor_id: int
    character_id: int
    event_id: int
    relation: str
    time: Stamp


class ActedCharacter(BaseModel):
    expansion_id: int
    actor: ActorPick
    intent: IntentDraft
    roll: str
    event: EventRecord
    arc_id: int | None = None
    idea_ids: list[int] = []
    characters: list[GeneratedCharacter] = []
    moves: list[CharacterMove] = []
    invited_ids: list[int] = []
    dialogue: list[DialogueTurn] = []
    frame: ImpactFrame | None = None
    narration: Narration | None = None


class ActFailure(BaseModel):
    expansion_id: int | None = None
    character_id: int | None = None
    name: str | None = None
    error: str


class ActRun(BaseModel):
    """一回の実行(`ActCharacter`)で打った手。裁く段はこの実行の手をまとめて一度だけ呼ぶ。"""

    acted: list[ActedCharacter] = []
    failed: list[ActFailure] = []
