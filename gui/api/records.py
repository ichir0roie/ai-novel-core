#!/usr/bin/env python3
"""行の一覧・一件・追加・修正。読むのは select で直接、書くのは入口の `execute(s)` 越し。

行は表ごとの `record_model`(入口のレスポンスと同じモデル)に詰め、API の型(`gui/api/models.py`)に渡すときに dump する。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field, SerializeAsAny, model_serializer
from sqlalchemy import Column, ColumnElement, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from data_access_logic.entrypoint import UnknownFieldError, loading, record_of
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.event.record import EventRecord
from data_access_logic.idea.links import Appearance, appearances
from data_access_logic.idea.record import IdeaRecord
from data_access_logic.label import clipped, label_of
from data_access_logic.material import Material
from data_access_logic.query import common_query
from data_access_logic.story.record import StoryRecord
from db.schema import Base, Character, ConfirmStatusType, Episode, Event, Story
from gui.api.models import Option, RecordList, RecordResponse
from gui.api.tables import TABLE_BY_NAME, TableSpec, spec_of

# エピソード画面の「関連」に出す出来事・話の件数の上限(時期だけで絞ると際限なく広がりうるため)
_CONTEXT_LIMIT = 100

# 参照先の名前。{列名: {id: 名前}}
Labels = dict[str, dict[int, str]]


class RecordSummary(BaseModel):
    """一覧の一行。行の欄から本文の列を外し、呼び名と本文の頭を同じ段に並べる。"""

    record: SerializeAsAny[Material]
    text_columns: tuple[str, ...] = Field(exclude=True)
    label: str
    preview: str

    @model_serializer(mode="wrap")
    def _flat(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        columns = data.pop("record")
        return {**{key: value for key, value in columns.items() if key not in self.text_columns}, **data}


class EpisodeLink(Appearance):
    synced: bool
    letters: int


class ContextBlock(BaseModel):
    items: list[RecordSummary]
    labels: Labels


class EpisodeContext(BaseModel):
    event: ContextBlock
    story: ContextBlock


class Related(BaseModel):
    """フォームに載せない、表示だけの関連情報。表ごとに持つ欄が違い、無い欄は画面に出さない。"""


class IdeaRelated(Related):
    appearances: list[Appearance]


class StoryRelated(Related):
    episodes: list[EpisodeLink]


class EpisodeRelated(Related):
    context: EpisodeContext


def _preview(spec: TableSpec, row: Base) -> str:
    for name in spec.model.TEXT_COLUMNS:
        value = (getattr(row, name) or "").strip()
        if value:
            return clipped(value)
    return ""


def summary_of(spec: TableSpec, row: Base) -> RecordSummary:
    """`row` は `loading` で読んだ行。"""
    return RecordSummary(record=spec.record_model.model_validate(row), text_columns=(*spec.model.TEXT_COLUMNS, "text"),
                         label=label_of(spec.model, row), preview=_preview(spec, row))


def reference_labels(s: Session, spec: TableSpec, records: list[Material]) -> Labels:
    """参照先(`*_id` の列と、出来事の当事者・話の登場人物)の名前を、参照先のテーブルごとに一回の select で引く。"""
    wanted: dict[str, dict[str, set[int]]] = {}
    for column in spec.model.__table__.columns:
        for foreign_key in column.foreign_keys:
            ids = {getattr(record, column.key) for record in records} - {None}
            wanted.setdefault(foreign_key.column.table.name, {})[column.key] = ids
    if spec.model in (Event, Episode):
        wanted.setdefault("character", {})["character_ids"] = {
            id_ for record in records if isinstance(record, (EventRecord, EpisodeRecord)) for id_ in record.character_ids}
    labels: Labels = {}
    for table, columns in wanted.items():
        target = TABLE_BY_NAME.get(table)
        ids = set().union(*columns.values())
        if target is None or not ids:
            continue
        rows = s.scalars(select(target.model).where(target.model.id.in_(ids))).all()
        names = {row.id: label_of(target.model, row) for row in rows}
        for key, column_ids in columns.items():
            labels[key] = {id_: names[id_] for id_ in column_ids if id_ in names}
    return labels


def _filter_value(column: Column, value: str) -> Any:
    if value == "null":
        return None
    if isinstance(column.type, ConfirmStatusType):
        return value
    python_type = getattr(column.type, "python_type", str)
    if python_type is bool:
        return value.lower() in ("1", "true", "yes", "on")
    if python_type in (int, float):
        return python_type(value)
    return value


def _ordering(model: type[Base], sort: str, order: str) -> list[ColumnElement[Any] | InstrumentedAttribute[Any]]:
    column = model.__table__.columns.get(sort)
    if column is None:
        raise UnknownFieldError(f"{model.__tablename__} に列 {sort} は無い")
    key = getattr(model, sort)
    desc = order == "desc"
    # 空の行はどちら向きでも後ろに、同じ値の中は id 順に
    return [key.is_(None), key.desc() if desc else key, model.id.desc() if desc else model.id]


def list_records(s: Session, spec: TableSpec, q: str | None, limit: int, offset: int,
                 sort: str, order: str, filters: dict[str, str]) -> RecordList:
    model = spec.model
    conditions = []
    if q:
        conditions.append(or_(*(getattr(model, name).contains(q, autoescape=True)
                                for name in spec.search_columns)))
    for key, value in filters.items():
        column = model.__table__.columns.get(key)
        if column is None or value == "":
            continue
        parsed = _filter_value(column, value)
        conditions.append(getattr(model, key).is_(None) if parsed is None else getattr(model, key) == parsed)
    total = s.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
    rows = s.scalars(loading(select(model).where(*conditions).order_by(*_ordering(model, sort, order))
                             .limit(limit).offset(offset), spec.record_model)).all()
    summaries = [summary_of(spec, row) for row in rows]
    return RecordList(total=total, limit=limit, offset=offset,
                      items=[summary.model_dump(mode="json") for summary in summaries],
                      labels=reference_labels(s, spec, [summary.record for summary in summaries]))


def options(s: Session, spec: TableSpec, q: str | None, limit: int, ids: list[int] | None = None) -> list[Option]:
    model = spec.model
    conditions = []
    if q:
        conditions.append(or_(*(getattr(model, name).contains(q, autoescape=True)
                                for name in spec.search_columns)))
    if ids:
        conditions.append(model.id.in_(ids))
    rows = s.scalars(select(model).where(*conditions).order_by(model.id).limit(limit)).all()
    parent_column = spec.tree_parent_column
    return [Option(id=row.id, label=label_of(model, row),
                   parent_id=getattr(row, parent_column) if parent_column else None,
                   born=str(row.start) if spec.model is Character and row.start is not None else None)
            for row in rows]


def _context_block(s: Session, table: str, rows: Sequence[Base]) -> ContextBlock:
    spec = spec_of(table)
    summaries = [summary_of(spec, row) for row in rows]
    return ContextBlock(items=summaries, labels=reference_labels(s, spec, [summary.record for summary in summaries]))


def _episode_context(s: Session, episode: EpisodeRecord) -> EpisodeContext:
    """話の時期(start〜end)・場所(location_id)に重なる出来事・作品。

    人物・場所はここでは拾わない(話の人物は `episode_character`、場所は `location_id` がそのまま持つ)。
    """
    since = episode.start
    until = episode.end or since
    location_ids = set(common_query.descendant_location_ids(s, episode.location_id)) if episode.location_id else set()

    event_conditions = [Event.time.between(since, until)]
    if location_ids:
        event_conditions.append(Event.location_id.in_(location_ids))
    events = s.scalars(loading(select(Event).where(*event_conditions)
                               .order_by(Event.time, Event.id).limit(_CONTEXT_LIMIT), EventRecord)).all()

    story_conditions = [Story.id != episode.story_id,
                        or_(Story.start.is_(None), Story.start <= until),
                        or_(Story.end.is_(None), Story.end >= since)]
    if location_ids:
        story_conditions.append(or_(Story.location_id.in_(location_ids), Story.world_id.in_(location_ids)))
    stories = s.scalars(select(Story).where(*story_conditions)
                        .order_by(Story.id).limit(_CONTEXT_LIMIT)).all()

    return EpisodeContext(event=_context_block(s, "event", events),
                          story=_context_block(s, "story", stories))


def related_of(s: Session, record: Material) -> Related:
    if isinstance(record, IdeaRecord):
        return IdeaRelated(appearances=appearances(s, record.id))
    if isinstance(record, StoryRecord):
        episodes = s.scalars(common_query.story_episodes_select(record.id)).all()
        return StoryRelated(episodes=[
            EpisodeLink(table=Episode.__tablename__, id=episode.id, label=label_of(Episode, episode),
                        synced=episode.synced, letters=episode.letters)
            for episode in episodes])
    # 時期の無い話は、重なる出来事・作品を出しようがない
    if isinstance(record, EpisodeRecord) and record.start is not None:
        return EpisodeRelated(context=_episode_context(s, record))
    return Related()


def response_of(s: Session, spec: TableSpec, record: Material) -> RecordResponse:
    return RecordResponse(record=record.model_dump(mode="json"), label=label_of(spec.model, record),
                          labels=reference_labels(s, spec, [record]),
                          related=related_of(s, record).model_dump(mode="json"))


def get_record(s: Session, spec: TableSpec, record_id: int) -> RecordResponse:
    row = common_query.get_row(s, spec.model, record_id)
    return response_of(s, spec, record_of(s, spec.record_model, row))


def create_record(s: Session, spec: TableSpec, data: dict[str, Any]) -> Material:
    return spec.creator(spec.create_form.model_validate(data)).execute(s)


def update_record(s: Session, spec: TableSpec, record_id: int, data: dict[str, Any]) -> Material:
    return spec.updater(spec.update_form(id=record_id, **data)).execute(s)
