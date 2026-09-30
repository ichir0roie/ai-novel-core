from typing import Annotated

from pydantic import Field, model_validator
from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from data_access_logic.episode.mentions import save_mentions
from data_access_logic.material import Draft, Form, References, Timestamp
from db.schema import Episode, EpisodeCharacter


class EpisodeForm(Draft):
    """話の下書き。"""

    id: int | None = None
    story_id: int | None = None
    title: str | None = None
    plot_text: str | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    viewpoint_character_id: int | None = None
    location_id: int | None = None
    character_ids: Annotated[list[int] | None, References("character")] = Field(
        default=None, title="登場人物",
        description="この話に出す人物。初めはこの話の登場人物(episode_character)。選んだ人物で登場人物を置き換える")


class EpisodeCommitForm(Form):
    """`id` を渡せばその話の渡した欄だけを直し、省けば `story_id` の作品に新しい話を足す。"""

    id: int | None = None
    story_id: int | None = None
    title: str | None = None
    plot_text: str | None = None
    # 改行を整えてから入れる(`layout_novel_text`)
    main_text: str | None = None
    start: Timestamp | None = None
    end: Timestamp | None = None
    viewpoint_character_id: int | None = None
    location_id: int | None = None
    event_seeded: bool | None = None
    # 渡さなければ、手で直した話として同期していない扱いにする
    synced: bool | None = None
    # 渡すと登場人物(`episode_character`)をまるごと置き換える
    character_ids: Annotated[list[int] | None, References("character")] = Field(
        default=None, title="登場人物", description="登場人物の id")

    @model_validator(mode="after")
    def _story_of_new_episode(self) -> "EpisodeCommitForm":
        if self.id is None and self.story_id is None:
            raise ValueError("story_id は必須(id を渡さず新しい話を足すとき)")
        return self


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


def save_frame(s: Session, form: EpisodeForm) -> Episode:
    """AI 呼び出し(数分〜十数分かかることがある)の前に下書きを保存しておき、途中で失敗しても編集を失わないようにする
    (呼ぶ側がこの後すぐ commit する)。名前だけ出る人物も、保存したプロット・本文から拾い直して、AI に渡す材料に入れる。"""
    if form.id is not None:
        record = s.get_one(Episode, form.id)
    elif form.story_id is not None:
        record = Episode(story_id=form.story_id, title="", plot_text="")
        s.add(record)
    else:
        raise ValueError("story_id は必須")

    if form.title is not None:
        record.title = form.title
    if form.plot_text is not None:
        record.plot_text = form.plot_text
    if form.start is not None:
        record.start = form.start
    if form.end is not None:
        record.end = form.end
    if form.viewpoint_character_id is not None:
        record.viewpoint_character_id = form.viewpoint_character_id
    if form.location_id is not None:
        record.location_id = form.location_id
    s.flush()
    if form.character_ids is not None:
        set_characters(s, record.id, form.character_ids)
    save_mentions(s, record.id)
    return record
