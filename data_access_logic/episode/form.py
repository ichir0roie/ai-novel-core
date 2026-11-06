from typing import Annotated

from pydantic import Field, model_validator
from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from data_access_logic.material import Form, References, Timestamp
from db.schema import EpisodeCharacter


class EpisodeCommitForm(Form):
    """`id` を渡せばその話の渡した欄だけを直し、省けば `story_id` の作品に新しい話を足す。"""

    id: int | None = None
    story_id: int | None = None
    title: str | None = None
    plot_text: str | None = None
    # 改行を整えてから入れる(`layout_novel_text`)
    main_text: str | None = None
    # この話の本文・プロットを書くときに足す指示
    instruction: str | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    viewpoint_character_id: int | None = None
    location_id: int | None = None
    # 渡すと登場人物(`episode_character`)をまるごと置き換える
    character_ids: Annotated[list[int] | None, References("character")] = Field(
        default=None, description="登場人物の id")

    @model_validator(mode="after")
    def _story_of_new_episode(self) -> "EpisodeCommitForm":
        if self.id is None and self.story_id is None:
            raise ValueError("story_id は必須(id を渡さず新しい話を足すとき)")
        return self


class EpisodeReviseForm(Form):
    """本文のある話の本文を直す(推敲)。時刻・登場人物・場所は変えない。"""

    id: int
    # 改行を整えてから入れる(`layout_novel_text`)
    main_text: str
    # 推敲の覚えを足したプロット。渡さなければそのまま
    plot_text: str | None = None
    # 題を直したときだけ渡す
    title: str | None = None


class EpisodeCreateForm(EpisodeCommitForm):
    """新しい話を足すときの `EpisodeCommitForm`(GUI の足す画面が必須の欄を示すのに使う)。"""

    id: None = None
    story_id: int = Field(...)


def set_characters(s: Session, episode_id: int, character_ids: list[int]) -> None:
    """登場人物を置き換える。名前だけ出る人物(`mentioned`)の行は、登場人物になった人物の分だけ消す。"""
    s.execute(delete(EpisodeCharacter).where(
        EpisodeCharacter.episode_id == episode_id,
        or_(EpisodeCharacter.mentioned.is_(False), EpisodeCharacter.character_id.in_(character_ids))))
    s.add_all([EpisodeCharacter(episode_id=episode_id, character_id=character_id)
               for character_id in dict.fromkeys(character_ids)])
    s.flush()


