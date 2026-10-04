import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.query import common_query
from db.schema import Idea, IdeaHistory

logger = logging.getLogger(__name__)


def _anchor(s: Session, location_id: int | None) -> tuple[Idea, int] | None:
    """場所の道筋を末端から遡り、その場所自身を表すアイデア(通常は「星」)が見つかった一番深いものと、その場所の id。
    アイデアの場所は履歴の行で持つ。"""
    if location_id is None:
        return None
    for step in reversed(common_query.location_path(s, location_id)):
        idea = s.scalar(
            select(Idea).join(IdeaHistory, IdeaHistory.idea_id == Idea.id)
            .where(Idea.kind == step.kind, IdeaHistory.location_id == step.id).order_by(Idea.id))
        if idea is not None:
            return idea, step.id
    return None


def find_or_create_classification(s: Session, kind: str, location_id: int | None) -> Idea | None:
    """`kind` をまとめる分類のアイデア(`name == kind` の行)を、`location_id` の属する世界・星を表すアイデアの下から探し、無ければその下に作る。
    場所を表すアイデアが見つからなければ、親を決めようがないので None(呼び出し側は `parent_idea_id` を付けない)。"""
    found = _anchor(s, location_id)
    if found is None:
        return None
    anchor, anchor_location_id = found
    existing = s.scalar(
        select(Idea).where(Idea.kind == kind, Idea.name == kind, Idea.parent_idea_id == anchor.id).order_by(Idea.id))
    if existing is not None:
        return existing
    # 分類は作中の人物が知るものではないので、知る相手の無い行で効く場所だけを持つ
    classification = Idea(
        name=kind, kind=kind, parent_idea_id=anchor.id, text=f'{anchor.name}における「{kind}」のアイデアをまとめる分類。',
        histories=[IdeaHistory(location_id=anchor_location_id, name=kind)])
    s.add(classification)
    s.flush()
    logger.info(f"分類を足した: {classification.name}(id={classification.id})")
    return classification
