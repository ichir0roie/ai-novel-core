from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import delete
from sqlalchemy.orm import Session

from data_access_logic.material import Form, Timestamp
from db.schema import Episode, EpisodeCharacter
from db.stamp import Stamp


class EpisodeForm(BaseModel):
    """GUI の欄・スキルの引数で渡る、話の下書き。空の欄は「指定なし」。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int | None = None
    story_id: int | None = None
    title: str | None = None
    key: str | None = None
    start: Stamp | None = None
    end: Stamp | None = None
    viewpoint_character_id: int | None = None
    place_id: int | None = None
    character_ids: list[int] | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("start", "end", mode="before")
    @classmethod
    def _stamp(cls, value: Any) -> Stamp | None:
        return Stamp.parse(value)


class EpisodeCommitForm(Form):
    """`id` を渡せばその話の渡した欄だけを直し、省けば `story_id` の作品に新しい話を足す。"""

    id: int | None = None
    story_id: int | None = None
    title: str | None = None
    key: str | None = None
    # 改行を整えてから入れる(`layout_novel_text`)
    text: str | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    viewpoint_character_id: int | None = None
    place_id: int | None = None
    event_seeded: bool | None = None
    # 渡すと登場人物(`episode_character`)をまるごと置き換える
    character_ids: list[int] | None = None

    @model_validator(mode="after")
    def _story_of_new_episode(self) -> "EpisodeCommitForm":
        if self.id is None and self.story_id is None:
            raise ValueError("story_id は必須(id を渡さず新しい話を足すとき)")
        return self


def set_characters(s: Session, episode_id: int, character_ids: list[int]) -> None:
    s.execute(delete(EpisodeCharacter).where(EpisodeCharacter.episode_id == episode_id))
    s.add_all([EpisodeCharacter(episode_id=episode_id, character_id=character_id)
               for character_id in dict.fromkeys(character_ids)])
    s.flush()


def save_frame(s: Session, form: EpisodeForm) -> Episode:
    """AI 呼び出し(数分〜十数分かかることがある)の前に下書きを保存しておき、途中で失敗しても編集を失わないようにする。"""
    if form.id is not None:
        record = s.get_one(Episode, form.id)
    elif form.story_id is not None:
        record = Episode(story_id=form.story_id, title="", key="")
        s.add(record)
    else:
        raise ValueError("story_id は必須")

    if form.title is not None:
        record.title = form.title
    if form.key is not None:
        record.key = form.key
    if form.start is not None:
        record.start = form.start
    if form.end is not None:
        record.end = form.end
    if form.viewpoint_character_id is not None:
        record.viewpoint_character_id = form.viewpoint_character_id
    if form.place_id is not None:
        record.place_id = form.place_id
    s.flush()
    if form.character_ids is not None:
        set_characters(s, record.id, form.character_ids)
    s.commit()
    return record
