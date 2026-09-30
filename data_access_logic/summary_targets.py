"""材料に要約で渡す話・出来事。AI に渡す前に、要約を本文に揃えておく。

材料を組む関数(`*_material`)は要約をそのまま読むだけで作り直さないので、先に `*_targets` で対象を引いて揃える。
手元では `refresh` が自分のセッションで、web のセッションでは `web_session/summary.py` が API 越しに揃える。
"""
from sqlalchemy.orm import Session

from data_access_logic.ai_client import AIClient
from data_access_logic.episode import summary as episode_summary
from data_access_logic.event import summary as event_summary
from data_access_logic.material import Material
from db.schema import Episode, Event


class SummaryTargets(Material):
    episode_ids: list[int] = []
    event_ids: list[int] = []


def refresh(s: Session, ai: AIClient, targets: SummaryTargets) -> None:
    for episode_id in dict.fromkeys(targets.episode_ids):
        episode_summary.summarize(s, ai, s.get_one(Episode, episode_id))
    for event_id in dict.fromkeys(targets.event_ids):
        event_summary.summarize(s, ai, s.get_one(Event, event_id))
