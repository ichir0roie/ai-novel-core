"""話の本文が踏まえたアイデアを、中間テーブル(`episode_idea`)で結ぶ。"""
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.idea.alias import called
from data_access_logic.idea.models import IdeaHistoryWholeMaterial, IdeaMaterial, LinkedIdeaMaterial
from data_access_logic.knowers import knowers_at
from data_access_logic.label import label_of
from db.schema import Episode, EpisodeIdea, Idea, IdeaHistory, Location
from db.stamp import Stamp


def link(s: Session, episode: Episode, ideas: list[Idea] | list[IdeaMaterial]) -> int:
    """結んだ件数を返す(既に結んであるものは数えない)。"""
    existing = set(s.scalars(select(EpisodeIdea.idea_id).where(EpisodeIdea.episode_id == episode.id)).all())
    added = 0
    for idea in ideas:
        if idea.id in existing:
            continue
        s.add(EpisodeIdea(episode_id=episode.id, idea_id=idea.id))
        existing.add(idea.id)
        added += 1
    s.flush()
    return added


def _history_at(s: Session, row: IdeaHistory, time: Stamp) -> IdeaHistoryWholeMaterial:
    return IdeaHistoryWholeMaterial(
        location=None if row.location_id is None else s.get_one(Location, row.location_id), start=row.start, end=row.end,
        name=row.name, detail=row.detail, private=row.private, knowers=knowers_at(s, row.knowers, time))


def linked_ideas_at(s: Session, episode: Episode, location_id: int | None, time: Stamp) -> list[LinkedIdeaMaterial]:
    """話に結んだアイデア。結んだ人物と同じく効く期間(`start` / `end`)では絞らず、呼び名をその場所・時刻に効く履歴から選び、
    その時刻までに始まった履歴の行をすべて添える(人物の来歴と同じく、先の行は出さない)。"""
    ideas = s.scalars(
        select(Idea).join(EpisodeIdea, EpisodeIdea.idea_id == Idea.id)
        .where(EpisodeIdea.episode_id == episode.id)
        .order_by(Idea.id)
    ).all()
    histories = called(s, [idea.id for idea in ideas], location_id, time)
    return [
        LinkedIdeaMaterial(
            idea=idea, history=histories.get(idea.id),
            histories=[_history_at(s, row, time)
                       for row in sorted(idea.histories, key=lambda row: (row.start is not None, row.start or 0))
                       if row.start is None or row.start <= time])
        for idea in ideas
    ]


class Appearance(BaseModel):
    """アイデアが出てきた所(結んでいる話)。"""

    table: str
    id: int
    label: str


def appearances(s: Session, idea_id: int) -> list[Appearance]:
    episodes = s.scalars(select(Episode).join(EpisodeIdea, EpisodeIdea.episode_id == Episode.id)
                         .where(EpisodeIdea.idea_id == idea_id).order_by(Episode.id)).all()
    return [Appearance(table=Episode.__tablename__, id=episode.id, label=label_of(Episode, episode))
            for episode in episodes]


def relink(s: Session, source_id: int, target_id: int | None) -> int:
    """`source_id` に結んである話を `target_id` へ付け替える(None なら外す)。動かした件数を返す。"""
    rows = s.scalars(select(EpisodeIdea).where(EpisodeIdea.idea_id == source_id)).all()
    episode_ids = [row.episode_id for row in rows]
    for row in rows:
        s.delete(row)
    if target_id is not None:
        linked = set(s.scalars(select(EpisodeIdea.episode_id).where(EpisodeIdea.idea_id == target_id)).all())
        s.add_all(EpisodeIdea(episode_id=episode_id, idea_id=target_id)
                  for episode_id in dict.fromkeys(episode_ids) if episode_id not in linked)
    s.flush()
    return len(rows)
