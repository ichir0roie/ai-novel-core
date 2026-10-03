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


class TurnState(Material):
    # turn: いまこの人物が動く番 / waiting: ほかの人物の番か、まだ要求が無い / closed: 話が終わった
    status: Literal["turn", "waiting", "closed"]
    # turn と closed のときの、この人物の行
    record: SessionRecord | None = None
