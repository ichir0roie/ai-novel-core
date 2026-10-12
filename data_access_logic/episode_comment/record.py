from datetime import datetime

from sqlalchemy.orm import joinedload

from data_access_logic.material import Material, Named
from db.schema import EpisodeCommentReaction


class CommentDiff(Material):
    id: int
    episode_id: int
    diff_text: str
    closing: bool
    created_at: datetime


class ReactionRecord(Material):
    LOAD_OPTIONS = (joinedload(EpisodeCommentReaction.character),)

    id: int
    episode_id: int
    diff_id: int
    # 空なら語り部
    character: Named | None = None
    stance: str
    quote: str | None = None
    text: str
    created_at: datetime


class DraftSaved(Material):
    episode_id: int
    # 保存した本文の字数
    letters: int
    # 足した差分。前に保存した本文と変わらなければ空
    diff: CommentDiff | None = None


class LatestDiff(Material):
    episode_id: int
    diff_id: int
