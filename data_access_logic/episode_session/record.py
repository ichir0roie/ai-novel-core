from typing import Literal

from sqlalchemy.orm import joinedload, selectinload

from data_access_logic.material import Material, Named, Timestamp
from db.schema import EpisodeCharacterSession


class Witness(Material):
    character_id: int


class SessionRecord(Material):
    LOAD_OPTIONS = (joinedload(EpisodeCharacterSession.character), selectinload(EpisodeCharacterSession.witnesses))

    id: int
    episode_id: int
    # 空なら語りの行
    character: Named | None = None
    witnesses: list[Witness]
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
    # 前の自分の番から後に、見聞きした語りとほかの人物の一手(`turns.seen_lines`)
    seen: list[str] = []
    request: str
    closing: bool


class PlayedTurn(Material):
    """人物役が読み直す、自分がもう動いた手番の行。時刻は渡さない(`character/knowledge.py`)。"""

    id: int
    seen: list[str] = []
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


class KnowerGap(Material):
    """登場人物の来歴の行のうち、ほかの登場人物の名前が出るのに、その人物が知る相手に入っていない行。"""

    history_id: int
    character: Named
    start: Timestamp
    description: str
    # 名前が出るが、話の時刻に知らない登場人物
    unknowing: list[Named]
