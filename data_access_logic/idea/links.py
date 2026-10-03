"""話の本文が踏まえたアイデアを、中間テーブル(`episode_idea`)で結ぶ。"""
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.idea.alias import called
from data_access_logic.idea.models import IdeaMaterial, RelatedIdeaMaterial
from data_access_logic.label import label_of
from db.schema import Episode, EpisodeIdea, Idea
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


def linked_ideas_at(s: Session, episode: Episode, location_id: int | None, time: Stamp) -> list[RelatedIdeaMaterial]:
    """話に結んだアイデア。結んだ人物と同じく効く期間(`start` / `end`)では絞らず、履歴(呼び名)だけを
    その場所・時刻に効くものから選ぶ。"""
    ideas = s.scalars(
        select(Idea).join(EpisodeIdea, EpisodeIdea.idea_id == Idea.id)
        .where(EpisodeIdea.episode_id == episode.id)
        .order_by(Idea.id)
    ).all()
    histories = called(s, [idea.id for idea in ideas], location_id, time)
    return [RelatedIdeaMaterial(idea=idea, history=histories.get(idea.id)) for idea in ideas]


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
