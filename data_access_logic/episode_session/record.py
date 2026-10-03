from typing import Any, Literal

from pydantic import model_serializer
from sqlalchemy.orm import joinedload

from data_access_logic.character.knowledge import AppearanceSerialized
from data_access_logic.material import Material, Named, Timestamp
from db.schema import EpisodeCharacterSession


class SessionRecord(Material):
    LOAD_OPTIONS = (joinedload(EpisodeCharacterSession.character),)

    id: int
    episode_id: int
    # イベントの行は空
    character: Named | None = None
    time: Timestamp | None = None
    is_event: bool
    request: str | None = None
    closing: bool
    thought: str | None = None
    action: str | None = None
    speech: str | None = None
    aim: str | None = None
    event: str | None = None


class SeenSerialized(Material):
    """人物役が前の自分の番から見た行。ほかの人物の内心・狙いは入れない。"""

    is_event: bool
    # 知っている人物なら名前。初対面なら空で、見た目を渡す
    name: str | None = None
    looks: AppearanceSerialized | None = None
    action: str | None = None
    speech: str | None = None
    event: str | None = None

    @model_serializer
    def _for_actor(self) -> dict[str, Any]:
        if self.is_event:
            return {"環境": self.event}
        who: dict[str, Any] = ({"人物": self.name} if self.looks is None
                               else {"人物": "名前を知らない人物", "見た目": self.looks.model_dump()})
        return {**who, "行動": self.action, "セリフ": self.speech, "環境の変化": self.event}


class TurnRecord(Material):
    """人物役が読む自分の番の行。時刻は渡さない(`character/knowledge.py`)。"""

    id: int
    request: str | None = None
    closing: bool
    # 前の自分の番からこの番までの、イベントの行とほかの人物の一手(古い順)
    seen: list[SeenSerialized] = []


class TurnState(Material):
    # turn: いまこの人物が動く番 / waiting: ほかの人物の番か、まだ要求が無い / closed: 話が終わった
    status: Literal["turn", "waiting", "closed"]
    # turn と closed のときの、この人物の行
    record: TurnRecord | None = None


class SessionCleared(Material):
    episode_id: int
    # 消した行の数
    deleted: int
