#!/usr/bin/env python3
"""`db/schema.py` の列の定義から、フォームを組み立てるための情報を作る。列の定義はここでは持たない。"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Integer, Numeric, func, select
from sqlalchemy.orm import Session

from db.child_lists import child_columns, child_model
from db.schema import (
    CONFIRM_STATUSES, MEME_CATEGORIES, PERSONALITY_LEVELS, ConfirmStatusType, PersonalityLevelType,
    PolygonType, StampType,
)
from gui.api import generate
from gui.api.models import ChildListMeta, ColumnMeta, TableMeta
from gui.api.tables import TABLES, TableSpec

# コメントより短い、フォームに出す見出し
_LABELS = {
    "id": "id", "name": "名前", "kind": "種別", "text": "本文", "start": "開始", "end": "終了",
    "title": "題", "key": "種(キーテキスト)", "category": "分類", "confirmed": "確認",
    "location_id": "場所", "parent_id": "親の場所", "story_id": "作品", "episode_id": "話",
    "character_id": "人物", "character_id_1": "人物 1", "character_id_2": "人物 2", "relation": "関係",
    "time": "時刻", "hidden": "隠す", "narration": "語り", "state": "状態", "world_id": "世界線",
    "place_id": "場所", "viewpoint": "視点", "place": "場所(自由記述)", "synced": "同期済み",
    "title": "題",
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


def column_meta(table: str, model: type, column, *, section: bool = False, markdown: bool = True,
                 readonly: bool = False) -> ColumnMeta:
    kind = _column_type(column)
    is_personality = isinstance(column.type, PersonalityLevelType)
    choices = (list(CONFIRM_STATUSES) if kind == "confirm"
               else list(PERSONALITY_LEVELS) if is_personality
               else _CHOICES.get((table, column.key)))
    references = None
    if not is_personality:
        # 性格列は personality_level への FK を持つが、GUI では id の参照選択ではなく
        # 上の choices(無/低/並/高/必)のプルダウンにする
        for foreign_key in column.foreign_keys:
            references = foreign_key.column.table.name
    required = (not column.nullable and not column.primary_key and column.default is None
                and column.server_default is None and not section)
    return ColumnMeta(
        key=column.key, label=_label(column.key, column.comment), type=kind, nullable=column.nullable,
        required=required, section=section, markdown=markdown, choices=choices, references=references,
        readonly=readonly or column.primary_key, comment=column.comment)


def _extra_columns(spec: TableSpec) -> list[ColumnMeta]:
    """入口が列の外で受け取る欄。"""
    extras = []
    if spec.name == "character":
        # 誕生・死亡(start/end)は専用の列を持たず、parameters の期間で表す(表・モーダルはそちらに出す)ので、
        # ここでは列として足さない。値自体は COMPUTED_COLUMNS として record には引き続き乗る
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
    sections = set(model.TEXT_COLUMNS)
    # 字数は本文から自動で数えるので、フォームでは直に書けない
    readonly_columns = {"letters"} if spec.name == "episode" else set()
    # AI 生成前の種は、AI が書く本文とは並べず、左側の欄の下にスクロール欄で置く
    side_columns = {"key"} if spec.name == "episode" else set()
    # 話の本文は小説の地の文なので、マークダウンとして解釈せずただのテキストとして扱う
    plain_text_columns = {"text"} if spec.name == "episode" else set()
    plain, long = [], []
    for column in model.__table__.columns:
        meta = column_meta(spec.name, model, column, section=column.key in sections,
                           readonly=column.key in readonly_columns,
                           markdown=column.key not in plain_text_columns)
        if column.key in side_columns:
            meta = meta.model_copy(update={"side": True})
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
                     reviewable=spec.reviewable, count=count, sort=spec.sort, order=spec.order,
                     generators=[generator.to_meta() for generator in generate.generators_of(spec.name)])


def all_tables(session: Session) -> list[TableMeta]:
    return [table_meta(session, spec) for spec in TABLES]


_LABELS["parameters"] = "期間ごとのパラメータ"
_LABELS["places"] = "期間ごとの居場所"
