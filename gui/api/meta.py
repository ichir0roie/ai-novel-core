#!/usr/bin/env python3
"""`db/schema.py` の列の定義と、入口の引数のモデル(`TableSpec.create_form` など)の欄から、フォームを組み立てるための情報を作る。
列の定義・欄の検証はここでは持たない。"""
from __future__ import annotations

import typing

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from sqlalchemy import Boolean, Column, Integer, JSON, Numeric, func, select
from sqlalchemy.orm import Session

from data_access_logic.label import LABEL_COLUMNS
from db.child_lists import child_columns, child_model
from db.schema import PolygonType, StampType
from gui.api.fields import choices_of, field_meta
from gui.api.models import ChildListMeta, ColumnMeta, TableMeta
from gui.api.tables import TABLES, TableSpec

# コメントより短い、フォームに出す見出し
_LABELS = {
    "id": "id", "name": "名前", "kind": "種別", "text": "本文", "start": "開始", "end": "終了",
    "appearance": "外見", "meme": "ミーム", "principle": "行動原理", "plot": "筋書き",
    "title": "題", "plot_text": "プロット", "main_text": "本文", "category": "分類",
    "location_id": "場所", "parent_id": "親の場所", "story_id": "作品", "episode_id": "話",
    "character_id": "人物", "character_1_id": "人物 1", "character_2_id": "人物 2", "relation": "関係",
    "time": "時刻", "hidden": "隠す", "narration": "語り", "state": "状態", "world_id": "世界線",
    "viewpoint_character_id": "視点", "synced": "同期済み",
    "meme_seeded": "ミーム抽出済み", "event_seeded": "出来事抽出済み", "main_character": "メインキャラクター",
    "parent_idea_id": "上位のアイデア", "parent_event_id": "親の出来事", "parent_story_id": "親の作品",
    "letters": "字数", "polygon": "領域(polygon)", "area": "広さ",
    "environment": "環境", "active_random_generation": "自動生成の対象", "description": "説明",
}


# CHILD_LISTS のうち、素朴な編集可能な表(既定の "table")以外の見せ方をする名前(`ChildListMeta.display`)。
# 対象・意味はテーブルごとに違うが見た目は共通の ChildListEditor を使う(`web/components/RecordForm.tsx`)。
_CHILD_LIST_DISPLAY: dict[str, dict[str, str]] = {
    "character": {"parameters": "periodic", "locations": "periodic", "histories": "flow"},
    "idea": {"recognitions": "flow", "histories": "flow"},
}


def _label(key: str, comment: str | None) -> str:
    if key in _LABELS:
        return _LABELS[key]
    if comment:
        return comment.split("。")[0]
    return key


def _column_type(column: Column) -> str:
    kind = column.type
    if isinstance(kind, StampType):
        return "stamp"
    if isinstance(kind, (PolygonType, JSON)):
        return "json"
    if isinstance(kind, Boolean):
        return "boolean"
    if isinstance(kind, Integer):
        return "integer"
    if isinstance(kind, Numeric):
        return "number"
    return "string"


def column_meta(column: Column, field: FieldInfo | None, section: bool = False, markdown: bool = True,
                readonly: bool = False, side: bool = False) -> ColumnMeta:
    """`field` は、その列に当たる入口の引数の欄(無ければ None)。選択肢と必須かどうかは、検証する欄のものを使う。"""
    choices = choices_of(field) if field is not None else None
    references = None
    if choices is None:
        # 性格列は personality_level への FK を持つが、GUI では id の参照選択ではなく、欄の型の選択肢(無/低/並/高/必)にする
        for foreign_key in column.foreign_keys:
            references = foreign_key.column.table.name
    if field is not None:
        required = field.is_required() and not section
    else:
        required = (not column.nullable and not column.primary_key and column.default is None
                    and column.server_default is None and not section)
    return ColumnMeta(
        key=column.key, label=_label(column.key, column.comment), type=_column_type(column), nullable=column.nullable,
        required=required, section=section, markdown=markdown, side=side, choices=choices, references=references,
        readonly=readonly or column.primary_key, comment=column.comment)


# 表の列でない欄のうち、フォームに出さないもの。人物の誕生・死亡は専用の列を持たず parameters の期間で表すので、
# 表・モーダルはそちらに出す(値自体は `CharacterRecord` の `start` / `end` として乗る)
_SHOWN_IN_CHILD_LISTS = {"character": ("start", "end")}


def _extra_columns(spec: TableSpec) -> list[ColumnMeta]:
    """入口が列の外で受け取る欄(出来事の当事者など)。足す入口にしか無い欄は足すときだけ渡せる。"""
    skipped = {"id", *spec.model.__table__.columns.keys(), *spec.model.CHILD_LISTS, *_SHOWN_IN_CHILD_LISTS.get(spec.name, ())}
    create_fields, update_fields = spec.create_form.model_fields, spec.update_form.model_fields
    extras = [field_meta(key, field, create_only=key not in update_fields)
              for key, field in create_fields.items() if key not in skipped]
    extras += [field_meta(key, field) for key, field in update_fields.items()
               if key not in skipped and key not in create_fields]
    return extras


def _row_model(spec: TableSpec, name: str) -> type[BaseModel]:
    """子の一覧の行のモデル(`list[CharacterParameterRow]` の中身)。"""
    fields = spec.create_form.model_fields if name in spec.create_form.model_fields else spec.update_form.model_fields
    for member in (fields[name].annotation, *typing.get_args(fields[name].annotation)):
        for argument in typing.get_args(member):
            if isinstance(argument, type) and issubclass(argument, BaseModel):
                return argument
    raise TypeError(f"{spec.name}.{name} の行のモデルが分からない")


def table_columns(spec: TableSpec) -> list[ColumnMeta]:
    model = spec.model
    sections = set(model.TEXT_COLUMNS)
    # 字数は本文から自動で数えるので、フォームでは直に書けない
    readonly_columns = {"letters"} if spec.name == "episode" else set()
    # 本文の概要は AI に前の話を渡すためのものなので、画面には出さない
    hidden_columns = {"summary_text", "summary_source_hash"} if spec.name == "episode" else set()
    # AI 生成前のプロットは、AI が書く本文とは並べず、左側の欄の下にスクロール欄で置く
    side_columns = {"plot_text"} if spec.name == "episode" else set()
    # 話の本文は小説の地の文なので、マークダウンとして解釈せずただのテキストとして扱う
    plain_text_columns = {"main_text"} if spec.name == "episode" else set()
    plain, long = [], []
    for column in model.__table__.columns:
        if column.key in hidden_columns:
            continue
        meta = column_meta(column, spec.create_form.model_fields.get(column.key), section=column.key in sections,
                           readonly=column.key in readonly_columns,
                           markdown=column.key not in plain_text_columns, side=column.key in side_columns)
        (long if meta.section else plain).append(meta)
    extras = _extra_columns(spec)
    return plain + [meta for meta in extras if not meta.section] + long + [meta for meta in extras if meta.section]


def child_lists(spec: TableSpec) -> list[ChildListMeta]:
    result = []
    display_by_name = _CHILD_LIST_DISPLAY.get(spec.name, {})
    for name in spec.model.CHILD_LISTS:
        child = child_model(spec.model, name)
        row_fields = _row_model(spec, name).model_fields
        columns = [column_meta(child.__table__.columns[key], row_fields.get(key)) for key in child_columns(spec.model, name)]
        result.append(ChildListMeta(name=name, label=_label(name, None), columns=columns,
                                    display=display_by_name.get(name, "table")))
    return result


def table_meta(s: Session, spec: TableSpec) -> TableMeta:
    count = s.scalar(select(func.count()).select_from(spec.model)) or 0
    return TableMeta(name=spec.name, label=spec.label, label_column=LABEL_COLUMNS[spec.model],
                     columns=table_columns(spec), child_lists=child_lists(spec),
                     count=count, sort=spec.sort, order=spec.order)


def all_tables(s: Session) -> list[TableMeta]:
    return [table_meta(s, spec) for spec in TABLES]


_LABELS["parameters"] = "期間ごとのパラメータ"
_LABELS["locations"] = "期間ごとの居場所"
_LABELS["histories"] = "来歴"
_LABELS["knowers"] = "知る相手"
_LABELS["recognitions"] = "場所・時代ごとの呼び名"
