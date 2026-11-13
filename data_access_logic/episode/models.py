from typing import Any

from pydantic import model_serializer

from ai.instructions.materials import EPISODE_BRIEF_NOTES
from data_access_logic.character.models import (
    CastCandidate, CastCandidateSerialized, CastingCandidate, CastingCandidateSerialized, CastMaterial, CastSerialized,
    CharacterMaterial, CharacterSecrets, MentionedMaterial, MentionedSerialized, secrets_for_prompt,
)
from data_access_logic.event.models import EventMaterial, EventSerialized
from data_access_logic.history_start import start_for_prompt
from data_access_logic.idea.models import (
    WholeIdeaMaterial, whole_idea_for_prompt,
)
from data_access_logic.location.models import LocationLine, LocationMaterial
from data_access_logic.material import Material, Named
from db.stamp import Stamp


class StoryMaterial(Material):
    id: int
    name: str
    text: str
    parent_story: "StoryMaterial | None" = None


class EpisodeBase(Material):
    title: str


class AppearedEpisode(EpisodeBase):
    id: int
    start: Stamp | None = None
    story: Named


class AppearedEpisodeText(AppearedEpisode):
    main_text: str


class CharacterEpisodeText(Material):
    """人物が関わった話(`episode_character` の一行)を、本文つきで。"""

    character: Named
    mentioned: bool
    episode: AppearedEpisodeText


class CastAppearance(Material):
    """人物たちが関わった話一つ。本文は、どれかの人物の一番新しい話のときだけ渡す(`with_text`)。"""

    episode: AppearedEpisodeText
    appeared: list[Named] = []
    mentioned: list[Named] = []
    with_text: bool = False


class RecentEpisode(Material):
    """登場人物の話し方を調整する根拠にする話。本文と、話し方の根拠にできるかを決める時刻だけを持つ。"""

    start: Stamp | None = None
    main_text: str




def _without_plot(sheet: dict[str, Any]) -> dict[str, Any]:
    # 筋書きは話の時刻より先の筋も含むので、本文を書く材料には渡さない
    return {key: value for key, value in sheet.items() if key != "筋書き"}


class CastEpisodesSerialized(Material):
    """人物たちが関わった話。このセッションの Claude が読む形に整形する。"""

    # 古い順
    appearances: list[CastAppearance]

    @model_serializer
    def _for_claude(self) -> list[dict[str, Any]]:
        return [{"話id": row.episode.id, "作品": row.episode.story.name, "題": row.episode.title,
                 "時刻": str(row.episode.start) if row.episode.start else None,
                 "登場": [character.name for character in row.appeared],
                 "名前だけ": [character.name for character in row.mentioned],
                 "本文": row.episode.main_text if row.with_text else None}
                for row in self.appearances]


def _location_lines(locations: list[LocationLine]) -> list[dict[str, Any]]:
    return [{"名前": location.name, "種別": location.kind, "説明": location.text, "環境": location.environment,
             "来歴(古い順)": [f"{start_for_prompt(history.start)}: {history.description}" for history in location.histories]}
            for location in locations]


def _story(story: StoryMaterial) -> dict[str, Any]:
    return {"作品名": story.name, "筋書き": story.text,
            "親の作品": None if story.parent_story is None else _story(story.parent_story)}


class BriefEpisode(EpisodeBase):
    id: int
    start: Stamp
    end: Stamp | None = None
    plot_text: str
    main_text: str
    viewpoint_character: CharacterMaterial | None = None


class EpisodeBrief(Material):
    story: StoryMaterial
    main_episode: BriefEpisode
    # 文体の見本にする、同じ作品の直前の話の本文。字数の上限まで。古い順
    style_samples: list[str]
    # 話の場所とその親。広い順。来歴は話の時刻の年まで
    locations: list[LocationLine]
    cast: list[CastMaterial]
    # 登場人物でなく、プロット・本文に名前が出るだけの人物
    mentioned: list[MentionedMaterial]
    # 登場人物・名前だけ出る人物の芯・来歴を誰が知っているか。人物 id ごと
    secrets: dict[int, CharacterSecrets]
    # プロット・話のセッションの行・今の本文から挙げた語に当たったアイデアとその上位、足した候補。
    # 呼び名は話の時刻・場所に効く履歴から。履歴の行は話の時刻までに始まったものをすべて添える
    ideas: list[WholeIdeaMaterial]
    # 古い順
    location_events: list[EventMaterial]
    later_events: list[EventMaterial]
    # 書き方の決まり(世界ごとの文体 `style_preference` と作品・話の指示)
    guide: str


def _place(location: LocationMaterial) -> dict[str, Any]:
    return {"場所id": location.id, "名前": location.name, "種別": location.kind}


def _viewpoint(character: CharacterMaterial | None) -> dict[str, Any] | None:
    return None if character is None else {"人物id": character.id, "名前": character.name}


class EpisodeBriefSerialized(EpisodeBrief):
    """このセッションの Claude が読む形に整形する。"""

    cast: list[CastSerialized]
    mentioned: list[MentionedSerialized]
    location_events: list[EventSerialized]
    later_events: list[EventSerialized]

    def _member(self, member: CastSerialized | MentionedSerialized) -> dict[str, Any]:
        return {"人物id": member.character.id, **_without_plot(member.model_dump()),
                **secrets_for_prompt(self.secrets[member.character.id])}

    # 読んだ Claude が登場人物・場所・視点を id で直すので、AI へ渡す形と違って id を残す
    @model_serializer
    def _for_claude(self) -> dict[str, Any]:
        episode = self.main_episode
        return {
            "材料の読み方": EPISODE_BRIEF_NOTES,
            "書き方": self.guide,
            "作品": _story(self.story),
            "文体の見本(古い順)": self.style_samples,
            "この話": {
                "話id": episode.id,
                "題": episode.title,
                "時刻": str(episode.start),
                "終わり": str(episode.end) if episode.end else None,
                "場所(広い順)": [{**_place(location), **line}
                               for location, line in zip(self.locations, _location_lines(self.locations))],
                "視点": _viewpoint(episode.viewpoint_character),
                "登場人物": [self._member(member) for member in self.cast],
                "名前だけ出る人物": [self._member(member) for member in self.mentioned],
                "設定": [{"アイデアid": whole.idea.id, **whole_idea_for_prompt(whole)} for whole in self.ideas],
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
    # 話の場所とその親。広い順
    locations: list[LocationMaterial]
    # 話の場所の直下にある場所
    child_locations: list[LocationMaterial]
    cast: list[CastCandidate]
    # 登場人物でなく、プロット・本文に名前が出るだけの人物
    mentioned: list[CastCandidate]
    # 登場人物・名前だけ出る人物のどちらでもない、登場人物と関係のある人物・話の場所にいる人物
    candidates: list[CastingCandidate]


class EpisodeCastingSerialized(EpisodeCasting):
    """このセッションの Claude が読む形に整形する。人物が関わった話は `cast_episodes` で読む。"""

    cast: list[CastCandidateSerialized]
    mentioned: list[CastCandidateSerialized]
    candidates: list[CastingCandidateSerialized]

    # 読んだ Claude が登場人物・場所・視点を id で結ぶので、AI へ渡す形と違って id を残す
    @model_serializer
    def _for_claude(self) -> dict[str, Any]:
        episode = self.main_episode
        return {
            "この話": {
                "話id": episode.id,
                "題": episode.title,
                "時刻": str(episode.start),
                "場所(広い順)": [_place(location) for location in self.locations],
                "視点": _viewpoint(episode.viewpoint_character),
                "プロット": episode.plot_text,
            },
            "登場人物": [member.model_dump() for member in self.cast],
            "名前だけ出る人物": [member.model_dump() for member in self.mentioned],
            "登場人物の候補": [member.model_dump() for member in self.candidates],
            "この場所の中の既知の場所": [_place(location) for location in self.child_locations],
        }
