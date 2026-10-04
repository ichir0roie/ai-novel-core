from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from data_access_logic.character.models import (
    CastCandidate, CastCandidateSerialized, CastMaterial, CastSerialized, CharacterMaterial, CharacterRelationLine,
    MentionedMaterial, MentionedSerialized, relations_for_prompt,
)
from data_access_logic.event.models import EventMaterial, EventSerialized
from data_access_logic.idea.models import IdeaContextMaterial, IdeaContextSerialized, RelatedIdeaMaterial, idea_for_prompt
from data_access_logic.location.models import LocationMaterial
from data_access_logic.material import Material, Named
from db.stamp import Stamp


class StoryMaterial(Material):
    name: str
    text: str
    narration: str
    state: str
    start: Stamp | None = None
    end: Stamp | None = None
    parent_story: "StoryMaterial | None" = None


class EpisodeBase(Material):
    title: str


class PastEpisode(EpisodeBase):
    id: int
    start: Stamp | None = None
    summary_text: str
    # 章・外伝をまたいで、人物が関わった話も渡すので、どの作品の話かを添える
    story: Named | None = None


class AppearedEpisode(EpisodeBase):
    id: int
    start: Stamp | None = None
    summary_text: str | None = None
    story: Named


class CharacterEpisode(Material):
    """人物が関わった話(`episode_character` の一行)。"""

    character_id: int
    mentioned: bool
    episode: AppearedEpisode


class RecentEpisode(Material):
    """文体の見本にする話。中身を読み取らせないので、本文だけを持つ。"""

    main_text: str


class UnwrittenEpisode(EpisodeBase):
    plot_text: str
    main_text: str

    @field_validator("main_text")
    @classmethod
    def _unwritten(cls, value: str) -> str:
        if value.strip():
            raise ValueError("本文の入っている話は書き換えない")
        return value


class TargetEpisode(UnwrittenEpisode):
    start: Stamp
    viewpoint_character: CharacterMaterial | None = None

    @field_validator("plot_text")
    @classmethod
    def _plotted(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("話のプロット(plot_text)が空")
        return value


class FrameEpisode(UnwrittenEpisode):
    start: Stamp | None = None
    end: Stamp | None = None
    location: LocationMaterial | None = None
    viewpoint_character: CharacterMaterial | None = None


def _past_episodes(past_episodes: list[PastEpisode]) -> list[dict[str, Any]]:
    return [
        {"作品": past.story.name if past.story else None, "題": past.title,
         "時刻": str(past.start) if past.start else None, "概要": past.summary_text}
        for past in past_episodes
    ]


def _appearance(link: CharacterEpisode) -> dict[str, Any]:
    return {"話id": link.episode.id, "作品": link.episode.story.name, "題": link.episode.title,
            "時刻": str(link.episode.start) if link.episode.start else None, "出方": "名前だけ" if link.mentioned else "登場"}


def _appearances(appearances: list[CharacterEpisode], character_id: int) -> list[dict[str, Any]]:
    return [_appearance(link) for link in appearances if link.character_id == character_id]


def _summarized_appearances(appearances: list[CharacterEpisode], character_id: int) -> list[dict[str, Any]]:
    """概要は作り直さず、そのときのまま読む(まだ無ければ null)。"""
    return [{**_appearance(link), "概要": link.episode.summary_text}
            for link in appearances if link.character_id == character_id]


def _style_samples(recent_episodes: list[RecentEpisode]) -> list[str]:
    return [recent.main_text for recent in recent_episodes]


def _location(locations: list[LocationMaterial]) -> str | None:
    return " > ".join(
        f"{location.name}({location.kind})" if location.kind else location.name
        for location in locations if location.name) or None


def _story(story: StoryMaterial) -> dict[str, Any]:
    return {"作品名": story.name, "筋書き": story.text, "語り": story.narration, "状態": story.state,
            "親の作品": None if story.parent_story is None else _story(story.parent_story)}


class EpisodeMaterial(Material):
    story: StoryMaterial
    main_episode: TargetEpisode
    # この話より前の、同じ作品の話と登場人物が関わった話(直前の話も含む)。古い順
    past_episodes: list[PastEpisode]
    # 文体の見本にする、同じ作品の直前の話。古い順
    recent_episodes: list[RecentEpisode]
    # 話の場所(無ければ作品の立つ場所)とその親。広い順
    locations: list[LocationMaterial]
    cast: list[CastMaterial]
    # 登場人物でなく、プロット・本文に名前が出るだけの人物
    mentioned: list[MentionedMaterial]
    # 登場人物のどれかが片側にいる関係
    relations: list[CharacterRelationLine]
    # 古い順
    location_events: list[EventMaterial]
    later_events: list[EventMaterial]
    ideas: IdeaContextMaterial


class EpisodeMaterialSerialized(EpisodeMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    cast: list[CastSerialized]
    mentioned: list[MentionedSerialized]
    location_events: list[EventSerialized]
    later_events: list[EventSerialized]
    ideas: IdeaContextSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        episode = self.main_episode
        return {
            "作品": _story(self.story),
            "前の話の概要(古い順)": _past_episodes(self.past_episodes),
            "文体の見本(古い順)": _style_samples(self.recent_episodes),
            "書く話": {
                "時刻": str(episode.start),
                "場所": _location(self.locations),
                "視点": episode.viewpoint_character.name if episode.viewpoint_character else None,
                "登場人物": [member.model_dump() for member in self.cast],
                "名前だけ出る人物": [member.model_dump() for member in self.mentioned],
                "登場人物の関係": relations_for_prompt(self.relations),
                "プロット": episode.plot_text,
            },
            "この場所の直近の出来事(古い順)": [
                event.model_dump() for event in self.location_events],
            "この時点より後に既に決まっている出来事": [
                event.model_dump() for event in self.later_events],
            "関係する設定": self.ideas.model_dump(),
        }


class EpisodePlotRequest(Material):
    material: EpisodeMaterial
    # 今のプロットに加えて、作者が新しいプロットに望むこと
    order: str | None = None


class EpisodePlotRequestSerialized(EpisodePlotRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    material: EpisodeMaterialSerialized

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {**self.material.model_dump(), "作者の注文": self.order}


class EpisodeCastingRequest(Material):
    material: EpisodeMaterial
    # 書き直したプロット。材料の「書く話」のプロット(書き直す前のプロット)と置き換わる
    plot_text: str
    # 話の場所の直下にある場所
    known_locations: list[LocationMaterial]
    # 登場人物でなく、新しいプロットに名前が出る既知の人物
    known_characters: list[MentionedMaterial]


class EpisodeCastingRequestSerialized(EpisodeCastingRequest):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    material: EpisodeMaterialSerialized
    known_characters: list[MentionedSerialized]

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {
            **self.material.model_dump(),
            "新しいプロット": self.plot_text,
            "この場所の中の既知の場所": [_location([location]) for location in self.known_locations],
            "新しいプロットに名前の出る既知の人物": [member.model_dump() for member in self.known_characters],
        }


class BriefEpisode(EpisodeBase):
    id: int
    start: Stamp
    end: Stamp | None = None
    synced: bool
    plot_text: str
    main_text: str
    viewpoint_character: CharacterMaterial | None = None


class EpisodeBrief(Material):
    story: StoryMaterial
    main_episode: BriefEpisode
    # この話より前の、同じ作品の話と登場人物が関わった話(直前の話も含む)。古い順
    past_episodes: list[PastEpisode]
    # 文体の見本にする、同じ作品の直前の話。古い順
    recent_episodes: list[RecentEpisode]
    # 話の場所(無ければ作品の立つ場所)とその親。広い順
    locations: list[LocationMaterial]
    cast: list[CastMaterial]
    # 登場人物でなく、プロット・本文に名前が出るだけの人物
    mentioned: list[MentionedMaterial]
    # 登場人物のどれかが片側にいる関係
    relations: list[CharacterRelationLine]
    # 登場人物それぞれが、この話より前に関わった話(作品を問わない)。古い順
    appearances: list[CharacterEpisode]
    # 話に結んだアイデア(`episode_idea`)。効く期間では絞らず、履歴(呼び名)は話の時刻・場所に効くもの
    ideas: list[RelatedIdeaMaterial]
    # 古い順
    location_events: list[EventMaterial]
    later_events: list[EventMaterial]
    # 書き方の決まり(システム固有の文体と、世界ごとの好み `style_preference`)
    guide: str


def _place(location: LocationMaterial) -> dict[str, Any]:
    return {"場所id": location.id, "名前": location.name, "種別": location.kind}


class EpisodeBriefSerialized(EpisodeBrief):
    """このセッションの Claude が読む形に整形する。"""

    cast: list[CastSerialized]
    mentioned: list[MentionedSerialized]
    location_events: list[EventSerialized]
    later_events: list[EventSerialized]

    # 読んだ Claude が登場人物・場所・視点を id で直すので、AI へ渡す形と違って id を残す
    @model_serializer
    def _for_claude(self) -> dict[str, Any]:
        episode = self.main_episode
        viewpoint = episode.viewpoint_character
        return {
            "書き方": self.guide,
            "作品": _story(self.story),
            "前の話の概要(古い順)": [{"話id": past.id, **entry}
                                     for past, entry in zip(self.past_episodes, _past_episodes(self.past_episodes))],
            "文体の見本(古い順)": _style_samples(self.recent_episodes),
            "この話": {
                "話id": episode.id,
                "題": episode.title,
                "時刻": str(episode.start),
                "終わり": str(episode.end) if episode.end else None,
                "同期": episode.synced,
                "場所(広い順)": [_place(location) for location in self.locations],
                "視点": None if viewpoint is None else {"人物id": viewpoint.id, "名前": viewpoint.name},
                "登場人物": [{"人物id": member.character.id, **member.model_dump(),
                          "関わった話(古い順)": _appearances(self.appearances, member.character.id)}
                         for member in self.cast],
                "名前だけ出る人物": [{"人物id": member.character.id, **member.model_dump()} for member in self.mentioned],
                "登場人物の関係": relations_for_prompt(self.relations),
                "関係する設定": [{"アイデアid": related.idea.id, **idea_for_prompt(related, with_text=True)} for related in self.ideas],
                "プロット": episode.plot_text,
                "今の本文": episode.main_text,
            },
            "この場所の直近の出来事(古い順)": [event.model_dump() for event in self.location_events],
            "この時点より後に既に決まっている出来事": [event.model_dump() for event in self.later_events],
        }


class CastingEpisode(EpisodeBase):
    id: int
    start: Stamp
    plot_text: str
    viewpoint_character: CharacterMaterial | None = None


class EpisodeCasting(Material):
    """本文の材料を読む前に、登場人物・場所を決める材料。"""

    main_episode: CastingEpisode
    # 話の場所(無ければ作品の立つ場所)とその親。広い順
    locations: list[LocationMaterial]
    # 話の場所の直下にある場所
    child_locations: list[LocationMaterial]
    cast: list[CastCandidate]
    # 登場人物でなく、プロット・本文に名前が出るだけの人物
    mentioned: list[CastCandidate]
    # 登場人物・名前だけ出る人物のどちらでもない、登場人物と関係のある人物・話の場所にいる人物
    candidates: list[CastCandidate]
    # 登場人物・名前だけ出る人物それぞれが、この話より前に関わった話(作品を問わない)。古い順
    appearances: list[CharacterEpisode]


class EpisodeCastingSerialized(EpisodeCasting):
    """このセッションの Claude が読む形に整形する。"""

    cast: list[CastCandidateSerialized]
    mentioned: list[CastCandidateSerialized]
    candidates: list[CastCandidateSerialized]

    # 読んだ Claude が登場人物・場所・視点を id で結ぶので、AI へ渡す形と違って id を残す
    @model_serializer
    def _for_claude(self) -> dict[str, Any]:
        episode = self.main_episode
        viewpoint = episode.viewpoint_character
        return {
            "この話": {
                "話id": episode.id,
                "題": episode.title,
                "時刻": str(episode.start),
                "場所(広い順)": [_place(location) for location in self.locations],
                "視点": None if viewpoint is None else {"人物id": viewpoint.id, "名前": viewpoint.name},
                "プロット": episode.plot_text,
            },
            "登場人物": [{**member.model_dump(),
                      "関わった話(古い順)": _summarized_appearances(self.appearances, member.character.id)}
                     for member in self.cast],
            "名前だけ出る人物": [{**member.model_dump(),
                          "関わった話(古い順)": _summarized_appearances(self.appearances, member.character.id)}
                         for member in self.mentioned],
            "登場人物の候補": [member.model_dump() for member in self.candidates],
            "この場所の中の既知の場所": [_place(location) for location in self.child_locations],
        }


class EpisodeFrameMaterial(Material):
    story: StoryMaterial
    main_episode: FrameEpisode
    # 古い順
    past_episodes: list[PastEpisode]
    # 作品の立つ場所とその親。広い順
    locations: list[LocationMaterial]
    cast: list[CastMaterial]
    # 登場人物でなく、プロット・本文に名前が出るだけの人物
    mentioned: list[MentionedMaterial]
    # 登場人物のどれかが片側にいる関係
    relations: list[CharacterRelationLine]
    later_events: list[EventMaterial]


class EpisodeFrameMaterialSerialized(EpisodeFrameMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    cast: list[CastSerialized]
    mentioned: list[MentionedSerialized]
    later_events: list[EventSerialized]

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        episode = self.main_episode
        return {
            "作品": {
                **_story(self.story),
                "立つ場所": _location(self.locations),
            },
            "前の話の概要(古い順)": _past_episodes(self.past_episodes),
            "登場人物": [member.model_dump() for member in self.cast],
            "名前だけ出る人物": [member.model_dump() for member in self.mentioned],
            "登場人物の関係": relations_for_prompt(self.relations),
            "この時点より後に既に決まっている出来事": [
                event.model_dump() for event in self.later_events],
            "作者の指定": {
                "題": episode.title.strip() or None,
                "プロット": episode.plot_text.strip() or None,
                "時刻": str(episode.start) if episode.start else None,
                "終わり": str(episode.end) if episode.end else None,
                "視点": episode.viewpoint_character.name if episode.viewpoint_character else None,
                "場所": episode.location.name if episode.location else None,
            },
        }


class EpisodeSource(Material):
    title: str
    main_text: str


class EpisodeSummarySource(EpisodeSource):
    """概要を作る話。書き戻すときに、概要にした本文のハッシュを添える。"""

    id: int
    source_hash: str


class EpisodeSourceSerialized(EpisodeSource):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {"題": self.title, "本文": self.main_text}


def _not_empty(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("空")
    return value


class EpisodePlotDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    plot_text: str = Field(description="この話の新しいプロット。今のプロットとそっくり置き換わる")

    @field_validator("plot_text")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _not_empty(value)


class EpisodeCharacterCandidateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    called: str = Field(description="新しいプロットでの呼び名")
    text: str = Field(description="人物像と、この話での役どころ")

    @field_validator("called", "text")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()


class EpisodeLocationCandidateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="名前")
    kind: str = Field(description="種別。店・屋敷・広場など")
    text: str = Field(description="説明")
    environment: str = Field(description="環境")

    @field_validator("name", "kind")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _not_empty(value)


class EpisodeCastingDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    characters: list[EpisodeCharacterCandidateDraft] | None = Field(
        description="新しいプロットに出てくるのに、登場人物にいない人物。いなければ null")
    location: EpisodeLocationCandidateDraft | None = Field(
        description="新しいプロットの主な舞台が、書く話の場所より細かく、この場所の中の既知の場所にも無いときの、その舞台。"
                    "それ以外は null")


class EpisodeFrameDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="サブタイトル。短く")
    plot_text: str = Field(description="プロット")
    start: str = Field(description="時刻。「年/月/日」の形")

    @field_validator("title", "start")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()

    @field_validator("plot_text")
    @classmethod
    def _plot_text(cls, value: str) -> str:
        return _not_empty(value)


class EpisodeSummaryDraft(BaseModel):
    # json schema として AI に渡すので、docstring を書くと description として AI に渡る
    model_config = ConfigDict(extra="forbid")

    summary_text: str = Field(description="概要")

    @field_validator("summary_text")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _not_empty(value)
