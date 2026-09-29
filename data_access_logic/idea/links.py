"""出来事・話・人物の本文が踏まえたアイデアを、中間テーブル(`event_idea` など)で結ぶ。"""
from typing import Callable

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute, Session

from data_access_logic.idea.models import IdeaMaterial
from data_access_logic.label import label_of
from db.schema import Base, Character, CharacterIdea, Episode, EpisodeIdea, Event, EventIdea, Idea


class _Link:
    # 列はクラス変数に書くとディスクリプタとして int に読まれてしまうので、インスタンス変数に持つ
    def __init__(
        self, owner: type[Event] | type[Episode] | type[Character], table: type[Base], owner_id: InstrumentedAttribute[int],
        idea_id: InstrumentedAttribute[int], row: Callable[[int, int], Base],
    ):
        self.owner = owner
        self.table = table
        self.owner_id = owner_id
        self.idea_id = idea_id
        self.row = row


_LINKS = (
    _Link(Event, EventIdea, EventIdea.event_id, EventIdea.idea_id,
          lambda owner_id, idea_id: EventIdea(event_id=owner_id, idea_id=idea_id)),
    _Link(Episode, EpisodeIdea, EpisodeIdea.episode_id, EpisodeIdea.idea_id,
          lambda owner_id, idea_id: EpisodeIdea(episode_id=owner_id, idea_id=idea_id)),
    _Link(Character, CharacterIdea, CharacterIdea.character_id, CharacterIdea.idea_id,
          lambda owner_id, idea_id: CharacterIdea(character_id=owner_id, idea_id=idea_id)),
)


def _link_of(record: Base) -> _Link:
    return next(link for link in _LINKS if isinstance(record, link.owner))


def link(s: Session, record: Event | Episode | Character, ideas: list[Idea] | list[IdeaMaterial]) -> int:
    """結んだ件数を返す(既に結んであるものは数えない)。"""
    table = _link_of(record)
    existing = set(s.scalars(select(table.idea_id).where(table.owner_id == record.id)).all())
    added = 0
    for idea in ideas:
        if idea.id in existing:
            continue
        s.add(table.row(record.id, idea.id))
        existing.add(idea.id)
        added += 1
    s.flush()
    return added


def linked_records(s: Session, idea_id: int) -> list[Event | Episode | Character]:
    """アイデアを結んでいる出来事・話・人物。テーブルごとに id 順で並べる(出来事・話・人物の順)。"""
    return [record for table in _LINKS for record in s.scalars(
        select(table.owner).join(table.table, table.owner_id == table.owner.id)
        .where(table.idea_id == idea_id).order_by(table.owner.id)).all()]


class Appearance(BaseModel):
    """アイデアが出てきた所(結んでいる出来事・話・人物)。"""

    table: str
    id: int
    label: str


def appearances(s: Session, idea_id: int) -> list[Appearance]:
    return [Appearance(table=record.__tablename__, id=record.id, label=label_of(type(record), record))
            for record in linked_records(s, idea_id)]


def relink(s: Session, source_id: int, target_id: int | None) -> int:
    """`source_id` に結んであるものを `target_id` へ付け替える(None なら外す)。動かした件数を返す。"""
    moved = 0
    for table in _LINKS:
        owner_ids = s.scalars(select(table.owner_id).where(table.idea_id == source_id)).all()
        for row in s.scalars(select(table.table).where(table.idea_id == source_id)).all():
            s.delete(row)
            moved += 1
        if target_id is None:
            continue
        linked = set(s.scalars(select(table.owner_id).where(table.idea_id == target_id)).all())
        s.add_all(table.row(owner_id, target_id) for owner_id in dict.fromkeys(owner_ids) if owner_id not in linked)
    s.flush()
    return moved
