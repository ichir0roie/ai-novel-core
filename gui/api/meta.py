#!/usr/bin/env python3
"""`db/schema.py` の列の定義から、フォームを組み立てるための情報を作る。列の定義はここでは持たない。"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Integer, Numeric, String, func, select
from sqlalchemy.orm import Session

from db.child_lists import child_columns, child_model
from db.schema import (
    CONFIRM_STATUSES, MEME_CATEGORIES, ConfirmStatusType, Meme, PolygonType, StampType,
)
from gui.api.models import ChildListMeta, ColumnMeta, TableMeta
from gui.api.tables import TABLES, TableSpec

# コメントより短い、フォームに出す見出し
_LABELS = {
    "id": "id", "name": "名前", "kind": "種別", "text": "本文", "start": "開始", "end": "終了",
    "title": "題", "key": "種(キーテキスト)", "category": "分類", "confirmed": "確認",
    "location_id": "場所", "parent_id": "親の場所", "story_id": "作品", "plot_id": "話",
    "character_id": "人物", "character_id_1": "人物 1", "character_id_2": "人物 2", "relation": "関係",
    "time": "時刻", "hidden": "隠す", "narration": "語り", "state": "状態", "world_id": "世界線",
    "place_id": "場所", "viewpoint": "視点", "place": "場所(自由記述)", "synced": "同期済み",
    "directory_path": "置き場所(ディレクトリ)", "filename": "ファイル名", "fact_check": "検証結果",
    "meme_seeded": "ミーム抽出済み", "event_seeded": "出来事抽出済み", "main_character": "メインキャラクター",
    "alias_of_idea_id": "呼び名の本質", "parent_idea_id": "上位のアイデア", "parent_event_id": "親の出来事",
    "letters": "字数", "character_ids": "当事者", "polygon": "領域(polygon)", "area": "広さ",
    "environment": "環境", "active_random_generation": "自動生成の対象",
}

_CHOICES = {("meme", "category"): list(MEME_CATEGORIES)}


def _label(key: str, comment: str | None) -> str:
    if key in _LABELS:
        return _LABELS[key]
    if comment:
        return comment.split("。")[0]
    return key


def _column_type(column) -> str:
    kind = column.type
    if isinstance(kind, StampType):
        return "stamp"
    if isinstance(kind, ConfirmStatusType):
        return "confirm"
    if isinstance(kind, (PolygonType, JSON)):
        return "json"
    if isinstance(kind, Boolean):
        return "boolean"
    if isinstance(kind, Integer):
        return "integer"
    if isinstance(kind, Numeric):
        return "number"
    return "string"


def column_meta(table: str, model: type, column, *, section: bool = False, readonly: bool = False) -> ColumnMeta:
    kind = _column_type(column)
    choices = list(CONFIRM_STATUSES) if kind == "confirm" else _CHOICES.get((table, column.key))
    references = None
    for foreign_key in column.foreign_keys:
        references = foreign_key.column.table.name
    required = (not column.nullable and not column.primary_key and column.default is None
                and column.server_default is None and not section)
    return ColumnMeta(
        key=column.key, label=_label(column.key, column.comment), type=kind, nullable=column.nullable,
        required=required, section=section, choices=choices, references=references,
        readonly=readonly or column.primary_key, comment=column.comment)


def _extra_columns(spec: TableSpec) -> list[ColumnMeta]:
    """入口が列の外で受け取る欄。"""
    extras = []
    if spec.name == "plot":
        extras.append(ColumnMeta(key="letters", label=_LABELS["letters"], type="integer", nullable=False,
                                 required=False, readonly=True, comment="本文の字数。本文から数える"))
        extras.append(ColumnMeta(key="text", label=_LABELS["text"], type="string", nullable=True,
                                 required=False, section=True, comment="本文(episode)。話の md の隣の .txt"))
    if spec.name == "character":
        extras.append(ColumnMeta(key="place_id", label="出自(場所)", type="integer", nullable=True,
                                 required=False, references="location", create_only=True,
                                 comment="足すときの出自。CharacterPlace の一番古い行になる"))
    if spec.name == "event":
        extras.append(ColumnMeta(key="character_ids", label=_LABELS["character_ids"], type="id_list",
                                 nullable=True, required=False, references="character",
                                 comment="居合わせた人物の id"))
    return extras


def table_columns(spec: TableSpec) -> list[ColumnMeta]:
    model = spec.model
    sections = set(model.TEXT_SECTIONS)
    plain, long = [], []
    for column in model.__table__.columns:
        meta = column_meta(spec.name, model, column, section=column.key in sections)
        (long if meta.section else plain).append(meta)
    extras = _extra_columns(spec)
    return plain + [meta for meta in extras if not meta.section] + long + [meta for meta in extras if meta.section]


def child_lists(spec: TableSpec) -> list[ChildListMeta]:
    result = []
    for name in spec.model.CHILD_LISTS:
        child = child_model(spec.model, name)
        keys = child_columns(spec.model, name)
        columns = [column_meta(child.__tablename__, child, child.__table__.columns[key]) for key in keys]
        result.append(ChildListMeta(name=name, label=_label(name, None), columns=columns))
    return result


def table_meta(session: Session, spec: TableSpec) -> TableMeta:
    count = session.scalar(select(func.count()).select_from(spec.model)) or 0
    return TableMeta(name=spec.name, label=spec.label, label_column=spec.label_column,
                     columns=table_columns(spec), child_lists=child_lists(spec),
                     reviewable=spec.reviewable, count=count)


def all_tables(session: Session) -> list[TableMeta]:
    return [table_meta(session, spec) for spec in TABLES]


_LABELS["parameters"] = "期間ごとのパラメータ"
