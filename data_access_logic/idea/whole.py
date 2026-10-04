"""話を書くセッションの Claude が作者の目で読むアイデア。

人物役には渡さず、人物が知ることのできる履歴の行だけを `character/knowledge.py` が渡す。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.idea.alias import called
from data_access_logic.idea.models import IdeaHistoryWholeMaterial, WholeIdeaMaterial
from data_access_logic.knowers import knowers_at
from db.schema import Idea, IdeaHistory, Location
from db.stamp import Stamp


def _history_at(s: Session, row: IdeaHistory, time: Stamp) -> IdeaHistoryWholeMaterial:
    return IdeaHistoryWholeMaterial(
        location=None if row.location_id is None else s.get_one(Location, row.location_id), start=row.start, end=row.end,
        name=row.name, detail=row.detail, knowers=knowers_at(s, row.knowers, time))


def whole_ideas(s: Session, idea_ids: list[int], location_id: int | None, time: Stamp) -> list[WholeIdeaMaterial]:
    """呼び名をその場所・時刻に効く履歴から選び、その時刻までに始まった履歴の行をすべて添える(人物の来歴と同じく、先の行は出さない)。"""
    ideas = s.scalars(
        select(Idea).where(Idea.id.in_(idea_ids)).order_by(Idea.id).execution_options(populate_existing=True)
    ).all()
    histories = called(s, [idea.id for idea in ideas], location_id, time)
    return [
        WholeIdeaMaterial(
            idea=idea, history=histories.get(idea.id),
            histories=[_history_at(s, row, time)
                       for row in sorted(idea.histories, key=lambda row: (row.start is not None, row.start or 0))
                       if row.start is None or row.start <= time])
        for idea in ideas
    ]
