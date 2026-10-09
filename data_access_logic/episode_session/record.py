from typing import Literal

from sqlalchemy.orm import joinedload

from data_access_logic.material import Material, Named, Timestamp
from db.schema import EpisodeCharacterSession


class SessionRecord(Material):
    LOAD_OPTIONS = (joinedload(EpisodeCharacterSession.character),)

    id: int
    episode_id: int
    character: Named
    time: Timestamp | None = None
    request: str
    closing: bool
    thought: str | None = None
    action: str | None = None
    speech: str | None = None
    aim: str | None = None


class SessionSince(Material):
    records: list[SessionRecord]
    # その話の行の総数。見る側が持つ行と食い違えば、途中の行が消えた(`ClearSession`)ので全部を引き直す
    count: int


class TurnRecord(Material):
    """人物役が読む自分の番の行。時刻は渡さない(`character/knowledge.py`)。"""

    id: int
    request: str
    closing: bool


class PlayedTurn(Material):
    """人物役が読み直す、自分がもう動いた手番の行。時刻は渡さない(`character/knowledge.py`)。"""

    id: int
    request: str
    thought: str | None = None
    action: str
    speech: str | None = None
    aim: str | None = None


class TurnState(Material):
    # turn: いまこの人物が動く番 / waiting: ほかの人物の番か、まだ要求が無い / closed: 話が終わった
    status: Literal["turn", "waiting", "closed"]
    # turn と closed のときの、この人物の行
    record: TurnRecord | None = None


class SessionCleared(Material):
    episode_id: int
    # 消した行の数
    deleted: int


class SessionIdeas(Material):
    """語り部が足した語の行き先。本文は返さず、名前だけ(語り部は設定を読まない)。"""

    # 候補のアイデアとして足したものの名前
    added: list[str]
    # 足さなかった語(既にあるアイデアに当たったか、人物・場所の名前)
    kept: list[str]
