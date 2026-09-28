#!/usr/bin/env python3
"""行の一覧・一件・追加・修正。読むのは select で直接、書くのは入口の `execute(session)` 越し。"""
from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ai.claude_code.interface._base import UnknownFieldError, UnknownRecordError
from ai.claude_code.interface.randomizer.commit_event import CommitEvent
from ai.time_keeper import idea_context
from data_access_logic.query import common_query
from db.schema import (
    Character, CharacterPlace, ConfirmStatusType, Episode, Event, EventCharacter, Location, Story,
)
from db.schema_pydantic import to_dict
from gui.api.models import Option, RecordList, RecordResponse
from gui.api.tables import TABLE_BY_NAME, TableSpec, spec_of

_PREVIEW_LENGTH = 80
# エピソード画面の「関連」に出す出来事・話の件数の上限(時期だけで絞ると際限なく広がりうるため)
_CONTEXT_LIMIT = 100


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


def _participant_ids(session: Session, event_id: int) -> list[int]:
    # `Event.event_characters` は noload なので、中間テーブルを直接引く
    return list(session.scalars(select(EventCharacter.character_id)
                                .where(EventCharacter.event_id == event_id).order_by(EventCharacter.id)))


def record_dict(session: Session, spec: TableSpec, row) -> dict:
    data = to_dict(row)
    if spec.model is Event:
        data["character_ids"] = _participant_ids(session, row.id)
    return data


def _summary_dict(session: Session, spec: TableSpec, row) -> dict:
    data = record_dict(session, spec, row)
    for name in spec.model.TEXT_COLUMNS:
        data.pop(name, None)
    data.pop("text", None)
    data["label"] = label_of(spec, row)
    data["preview"] = _preview(spec, row)
    return data


def reference_labels(session: Session, spec: TableSpec, records: list[dict]) -> dict[str, dict[int, str]]:
    """参照先(`*_id` の列と、出来事の当事者)の名前を、参照先のテーブルごとに一回の select で引く。"""
    wanted: dict[str, dict[str, set[int]]] = {}
    for column in spec.model.__table__.columns:
        for foreign_key in column.foreign_keys:
            table = foreign_key.column.table.name
            ids = {record[column.key] for record in records if record.get(column.key) is not None}
            wanted.setdefault(table, {})[column.key] = ids
    if spec.model is Event:
        wanted.setdefault("character", {})["character_ids"] = {
            id_ for record in records for id_ in record.get("character_ids", [])}
    result: dict[str, dict[int, str]] = {}
    for table, columns in wanted.items():
        target = TABLE_BY_NAME.get(table)
        ids = set().union(*columns.values())
        if target is None or not ids:
            continue
        rows = session.scalars(select(target.model).where(target.model.id.in_(ids))).all()
        names = {row.id: label_of(target, row) for row in rows}
        for key in columns:
            result[key] = {id_: names[id_] for id_ in columns[key] if id_ in names}
    return result


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


def list_records(session: Session, spec: TableSpec, *, q: str | None, limit: int, offset: int,
                 sort: str = "id", order: str = "desc", filters: dict[str, str]) -> RecordList:
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
    rows = session.scalars(select(model).where(*conditions).order_by(*_ordering(model, sort, order))
                           .limit(limit).offset(offset)).all()
    items = [_summary_dict(session, spec, row) for row in rows]
    return RecordList(total=total, limit=limit, offset=offset, items=items,
                      labels=reference_labels(session, spec, items))


def options(session: Session, spec: TableSpec, *, q: str | None, limit: int, ids: list[int] | None = None) -> list[Option]:
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
                   parent_id=getattr(row, parent_column) if parent_column else None) for row in rows]


def _get(session: Session, spec: TableSpec, record_id: int):
    row = session.get(spec.model, record_id)
    if row is None:
        raise UnknownRecordError(f"{spec.name} に id={record_id} の行が無い")
    return row


def _place_ids_from_text(session: Session, text: str | None) -> set[int]:
    """話の場所欄(自由記述)に名前が出てくる場所を拾い、その配下も含めて id を返す。"""
    if not text:
        return set()
    names = session.execute(select(Location.id, Location.name).where(Location.name.isnot(None))).all()
    matched = [location_id for location_id, name in names if name and name in text]
    place_ids: set[int] = set()
    for location_id in matched:
        place_ids.update(common_query.descendant_place_ids(session, location_id))
    return place_ids


def _context_block(session: Session, table: str, rows) -> dict:
    spec = spec_of(table)
    items = [_summary_dict(session, spec, row) for row in rows]
    return {"items": items, "labels": reference_labels(session, spec, items)}


def _episode_context(session: Session, episode: Episode) -> dict:
    """話の時期(start〜end)・場所(自由記述)に重なる出来事・人物・場所・作品。時期の無い話は出しようがない。"""
    since = episode.start
    if since is None:
        return {}
    until = episode.end or since
    place_ids = _place_ids_from_text(session, episode.place)

    event_conditions = [Event.time.between(since, until)]
    if place_ids:
        event_conditions.append(Event.location_id.in_(place_ids))
    events = session.scalars(select(Event).where(*event_conditions)
                            .order_by(Event.time, Event.id).limit(_CONTEXT_LIMIT)).all()

    character_ids = set(session.scalars(
        select(EventCharacter.character_id).where(EventCharacter.event_id.in_([e.id for e in events]))))
    if place_ids:
        character_ids.update(session.scalars(
            select(CharacterPlace.character_id).where(
                CharacterPlace.location_id.in_(place_ids),
                or_(CharacterPlace.start.is_(None), CharacterPlace.start <= until),
                or_(CharacterPlace.end.is_(None), CharacterPlace.end >= since))))
    characters = (session.scalars(select(Character).where(Character.id.in_(character_ids))
                                 .order_by(Character.id)).all() if character_ids else [])

    location_ids = place_ids | {e.location_id for e in events if e.location_id is not None}
    locations = (session.scalars(select(Location).where(Location.id.in_(location_ids))
                                .order_by(Location.id)).all() if location_ids else [])

    story_conditions = [Story.id != episode.story_id,
                       or_(Story.start.is_(None), Story.start <= until),
                       or_(Story.end.is_(None), Story.end >= since)]
    if place_ids:
        story_conditions.append(or_(Story.place_id.in_(place_ids), Story.world_id.in_(place_ids)))
    stories = session.scalars(select(Story).where(*story_conditions)
                             .order_by(Story.id).limit(_CONTEXT_LIMIT)).all()

    return {"event": _context_block(session, "event", events),
            "character": _context_block(session, "character", characters),
            "location": _context_block(session, "location", locations),
            "story": _context_block(session, "story", stories)}


def related_of(session: Session, spec: TableSpec, row) -> dict:
    """フォームに載せない、表示だけの関連情報。"""
    related: dict = {}
    if spec.name == "idea":
        related["appearances"] = [
            {"table": table, "id": record.id, "label": label_of(spec_of(table), record)}
            for table, records in idea_context.linked_records(session, row.id).items()
            for record in records]
    if spec.name == "story":
        episodes = session.scalars(select(Episode).where(Episode.story_id == row.id)
                                .order_by(*_ordering(Episode, "start", "asc"))).all()
        related["episodes"] = [{"table": "episode", "id": episode.id, "label": label_of(spec_of("episode"), episode),
                             "synced": episode.synced, "letters": episode.letters}
                            for episode in episodes]
    if spec.name == "episode":
        related["context"] = _episode_context(session, row)
    return related


def get_record(session: Session, spec: TableSpec, record_id: int) -> RecordResponse:
    row = _get(session, spec, record_id)
    record = record_dict(session, spec, row)
    return RecordResponse(record=record, label=label_of(spec, row),
                          labels=reference_labels(session, spec, [record]), related=related_of(session, spec, row))


def _set_participants(session: Session, event_id: int, character_ids) -> None:
    ids = [int(id_) for id_ in character_ids or []]
    for character_id in ids:
        CommitEvent.check_exists(session, Character, character_id, "character_ids")
    session.execute(delete(EventCharacter).where(EventCharacter.event_id == event_id))
    session.add_all([EventCharacter(event_id=event_id, character_id=character_id) for character_id in ids])
    session.flush()


def create_record(session: Session, spec: TableSpec, data: dict) -> int:
    payload = dict(data)
    payload.pop("id", None)
    result = spec.creator(payload).execute(session)
    return int(result["id"])


def update_record(session: Session, spec: TableSpec, record_id: int, data: dict) -> None:
    _get(session, spec, record_id)
    payload = dict(data)
    payload.pop("id", None)
    character_ids = payload.pop("character_ids", None) if spec.name == "event" else None
    if spec.name == "character":
        payload.pop("place_id", None)  # 出自は足すときだけ。あとから直すのは CHILD_LISTS の places
    synced = payload.pop("synced", None) if spec.name == "episode" else None
    if payload:
        spec.updater({**payload, "id": record_id}).execute(session)
    if character_ids is not None:
        _set_participants(session, record_id, character_ids)
    if synced is not None:
        # CommitEpisode は直すたびに synced を落とす(本文を手で直したら世界観へ戻し直すため)。
        # GUI で明示的に渡された値はユーザの判断なのでそれを勝たせる
        session.get(Episode, record_id).synced = bool(synced)
        session.flush()
