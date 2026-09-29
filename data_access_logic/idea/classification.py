import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.query import common_query
from db.schema import ConfirmStatus, Idea

logger = logging.getLogger(__name__)


def _anchor(s: Session, location_id: int | None) -> Idea | None:
    """場所の道筋を末端から遡り、その場所自身を表すアイデア(通常は「星」)が見つかった一番深いもの。"""
    if location_id is None:
        return None
    for step in reversed(common_query.location_path(s, location_id)):
        idea = s.scalar(select(Idea).where(Idea.kind == step.kind, Idea.location_id == step.id).order_by(Idea.id))
        if idea is not None:
            return idea
    return None


def find_or_create_classification(s: Session, kind: str, location_id: int | None) -> Idea | None:
    """`kind` をまとめる分類のアイデア(`name == kind` の行)を、`location_id` の属する世界・星から探し、無ければその下に作る。
    場所を表すアイデアが見つからなければ、親を決めようがないので None(呼び出し側は `parent_idea_id` を付けない)。"""
    anchor = _anchor(s, location_id)
    if anchor is None:
        return None
    existing = s.scalar(
        select(Idea).where(Idea.kind == kind, Idea.name == kind, Idea.location_id == anchor.location_id)
        .order_by(Idea.id))
    if existing is not None:
        return existing
    classification = Idea(
        name=kind, kind=kind, confirmed=ConfirmStatus.APPROVED, parent_idea_id=anchor.id,
        location_id=anchor.location_id, text=f'{anchor.name}における「{kind}」のアイデアをまとめる分類。')
    s.add(classification)
    s.flush()
    logger.info(f"分類を足した: {classification.name}(id={classification.id})")
    return classification
