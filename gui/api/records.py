#!/usr/bin/env python3
"""行の一覧・一件・追加・修正。読むのは select で直接、書くのは入口の `execute(session)` 越し。

行は表ごとの `record_model`(入口のレスポンスと同じモデル)に詰め、API の型(`gui/api/models.py`)に渡すときに dump する。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, SerializeAsAny, model_serializer
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ai.claude_code.interface._base import UnknownFieldError, UnknownRecordError
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.event.record import EventRecord
from data_access_logic.idea.links import linked_records
from data_access_logic.material import Material
from data_access_logic.query import common_query
from db.schema import Character, ConfirmStatusType, Episode, Event, Idea, Story
from gui.api.models import Option, RecordList, RecordResponse
from gui.api.tables import TABLE_BY_NAME, TableSpec, spec_of

_PREVIEW_LENGTH = 80
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


class RecordLink(BaseModel):
    table: str
    id: int
    label: str


class EpisodeLink(RecordLink):
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
    appearances: list[RecordLink]


class StoryRelated(Related):
    episodes: list[EpisodeLink]


class EpisodeRelated(Related):
    context: EpisodeContext


def label_of(spec: TableSpec, row) -> str:
    if spec.label_column:
        value = getattr(row, spec.label_column, None)
        if value:
            return str(value)
    for name in spec.model.TEXT_COLUMNS:
        value = (getattr(row, name, None) or "").strip()
        if value:
            first = value.splitlines()[0]
            return first[:_PREVIEW_LENGTH] + ("…" if len(first) > _PREVIEW_LENGTH else "")
    return f"id={row.id}"


def _preview(spec: TableSpec, row) -> str:
    for name in spec.model.TEXT_COLUMNS:
        value = (getattr(row, name, None) or "").strip()
        if value:
            return value[:_PREVIEW_LENGTH] + ("…" if len(value) > _PREVIEW_LENGTH else "")
    return ""


def loaded(spec: TableSpec, query):
    """当事者・登場人物は noload なので、同じセッションに行が残っていても読み直す。"""
    return query.options(*spec.load_options).execution_options(populate_existing=True)


def record_of(spec: TableSpec, row) -> Material:
    return spec.record_model.model_validate(row)


def _summary(spec: TableSpec, row) -> RecordSummary:
    return RecordSummary(record=record_of(spec, row), text_columns=(*spec.model.TEXT_COLUMNS, "text"),
                         label=label_of(spec, row), preview=_preview(spec, row))


def reference_labels(session: Session, spec: TableSpec, records: list[Material]) -> Labels:
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
        rows = session.scalars(select(target.model).where(target.model.id.in_(ids))).all()
        names = {row.id: label_of(target, row) for row in rows}
        for key, column_ids in columns.items():
            labels[key] = {id_: names[id_] for id_ in column_ids if id_ in names}
    return labels


def _filter_value(column, value: str):
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


def _ordering(model, sort: str, order: str):
    column = model.__table__.columns.get(sort)
    if column is None:
        raise UnknownFieldError(f"{model.__tablename__} に列 {sort} は無い")
    key = getattr(model, sort)
    desc = order == "desc"
    # 空の行はどちら向きでも後ろに、同じ値の中は id 順に
    return [key.is_(None), key.desc() if desc else key, model.id.desc() if desc else model.id]


def list_records(session: Session, spec: TableSpec, q: str | None, limit: int, offset: int,
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
    total = session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
    rows = session.scalars(loaded(spec, select(model).where(*conditions).order_by(*_ordering(model, sort, order))
                                   .limit(limit).offset(offset))).all()
    summaries = [_summary(spec, row) for row in rows]
    return RecordList(total=total, limit=limit, offset=offset,
                      items=[summary.model_dump(mode="json") for summary in summaries],
                      labels=reference_labels(session, spec, [summary.record for summary in summaries]))


def options(session: Session, spec: TableSpec, q: str | None, limit: int, ids: list[int] | None = None) -> list[Option]:
    model = spec.model
    conditions = []
    if q:
        conditions.append(or_(*(getattr(model, name).contains(q, autoescape=True)
                                for name in spec.search_columns)))
    if ids:
        conditions.append(model.id.in_(ids))
    rows = session.scalars(select(model).where(*conditions).order_by(model.id).limit(limit)).all()
    parent_column = spec.tree_parent_column
    return [Option(id=row.id, label=label_of(spec, row),
                   parent_id=getattr(row, parent_column) if parent_column else None,
                   born=str(row.start) if spec.model is Character and row.start is not None else None)
            for row in rows]


def get_row(session: Session, spec: TableSpec, record_id: int):
    row = session.scalars(loaded(spec, select(spec.model).where(spec.model.id == record_id))).one_or_none()
    if row is None:
        raise UnknownRecordError(f"{spec.name} に id={record_id} の行が無い")
    return row


def _context_block(session: Session, table: str, rows) -> ContextBlock:
    spec = spec_of(table)
    summaries = [_summary(spec, row) for row in rows]
    return ContextBlock(items=summaries, labels=reference_labels(session, spec, [summary.record for summary in summaries]))


def _episode_context(session: Session, episode: Episode) -> EpisodeContext:
    """話の時期(start〜end)・場所(place_id)に重なる出来事・作品。

    人物・場所はここでは拾わない(話の人物は `episode_character`、場所は `place_id` がそのまま持つ)。
    """
    since = episode.start
    until = episode.end or since
    place_ids = set(common_query.descendant_place_ids(session, episode.place_id)) if episode.place_id else set()

    event_conditions = [Event.time.between(since, until)]
    if place_ids:
        event_conditions.append(Event.location_id.in_(place_ids))
    events = session.scalars(loaded(spec_of("event"), select(Event).where(*event_conditions)
                                     .order_by(Event.time, Event.id).limit(_CONTEXT_LIMIT))).all()

    story_conditions = [Story.id != episode.story_id,
                        or_(Story.start.is_(None), Story.start <= until),
                        or_(Story.end.is_(None), Story.end >= since)]
    if place_ids:
        story_conditions.append(or_(Story.place_id.in_(place_ids), Story.world_id.in_(place_ids)))
    stories = session.scalars(select(Story).where(*story_conditions)
                              .order_by(Story.id).limit(_CONTEXT_LIMIT)).all()

    return EpisodeContext(event=_context_block(session, "event", events),
                          story=_context_block(session, "story", stories))


def related_of(session: Session, spec: TableSpec, row) -> Related:
    if spec.model is Idea:
        return IdeaRelated(appearances=[
            RecordLink(table=record.__tablename__, id=record.id, label=label_of(spec_of(record.__tablename__), record))
            for record in linked_records(session, row.id)])
    if spec.model is Story:
        episodes = session.scalars(select(Episode).where(Episode.story_id == row.id)
                                   .order_by(*_ordering(Episode, "start", "asc"))).all()
        return StoryRelated(episodes=[
            EpisodeLink(table=Episode.__tablename__, id=episode.id, label=label_of(spec_of("episode"), episode),
                        synced=episode.synced, letters=episode.letters)
            for episode in episodes])
    # 時期の無い話は、重なる出来事・作品を出しようがない
    if spec.model is Episode and row.start is not None:
        return EpisodeRelated(context=_episode_context(session, row))
    return Related()


def get_record(session: Session, spec: TableSpec, record_id: int) -> RecordResponse:
    row = get_row(session, spec, record_id)
    record = record_of(spec, row)
    return RecordResponse(record=record.model_dump(mode="json"), label=label_of(spec, row),
                          labels=reference_labels(session, spec, [record]),
                          related=related_of(session, spec, row).model_dump(mode="json"))


def create_record(session: Session, spec: TableSpec, data: dict[str, Any]) -> int:
    return spec.creator(spec.create_form.model_validate(data)).execute(session).id


def update_record(session: Session, spec: TableSpec, record_id: int, data: dict[str, Any]) -> None:
    get_row(session, spec, record_id)
    spec.updater(spec.update_form.model_validate({**data, "id": record_id})).execute(session)
