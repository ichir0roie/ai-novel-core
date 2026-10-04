"""材料に要約で渡す話・出来事。AI に渡す前に、要約を本文に揃えておく。

材料を組む関数(`*_material`)は要約をそのまま読むだけで作り直さないので、先に `*_targets` で対象を引いて揃える。
手元ではここの関数が自分のセッションで、web のセッションでは `web_session/summary.py` が API 越しに、同じ形で揃える
(古い要約の元を一度に引き、AI の結果は得たその場で一件ずつ書き戻して commit する)。
"""
import logging

from sqlalchemy.orm import Session

from data_access_logic.ai_client import AIClient
from data_access_logic.episode import summary as episode_summary
from data_access_logic.event import summary as event_summary
from data_access_logic.material import Material
from db.schema import Episode

logger = logging.getLogger(__name__)


class SummaryTargets(Material):
    episode_ids: list[int] = []
    event_ids: list[int] = []


def rewrite_episode_summaries(
    s: Session, ai: AIClient, episode_ids: list[int] | None, stale_only: bool = True,
) -> list[Episode]:
    """`episode_ids` を省けばすべての話。`stale_only` を false にすると、本文が変わっていなくても作り直す。"""
    written = []
    for source in episode_summary.summary_sources(s, episode_ids, stale_only):
        draft = episode_summary.summary_draft(ai, source)
        if draft is None:
            logger.warning(f"話 id={source.id} の概要を作れなかった(AI が答えなかった)")
            continue
        written.append(episode_summary.write_summary(s, source.id, source.source_hash, draft.summary_text))
        s.commit()
    return written


def rewrite_event_summaries(s: Session, ai: AIClient, event_ids: list[int] | None) -> int:
    """`event_ids` を省けばすべての出来事。要約が本文と食い違っている出来事だけを作り直し、作り直した件数を返す。"""
    written = 0
    for source in event_summary.stale_sources(s, event_ids):
        draft = event_summary.summary_draft(ai, source)
        if draft is None:
            logger.warning(f"出来事 id={source.id} の要約を作れなかった(AI が答えなかった)")
            continue
        event_summary.write_summary(s, source.id, source.source_hash, draft.text)
        s.commit()
        written += 1
    return written


def refresh(s: Session, ai: AIClient, targets: SummaryTargets) -> None:
    if targets.episode_ids:
        rewrite_episode_summaries(s, ai, list(dict.fromkeys(targets.episode_ids)))
    if targets.event_ids:
        rewrite_event_summaries(s, ai, list(dict.fromkeys(targets.event_ids)))
