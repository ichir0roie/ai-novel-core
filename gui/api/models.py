#!/usr/bin/env python3
"""API の入出力の形。OpenAPI に出て、フロント(`gui/web`)の型(`lib/openapi.d.ts`)の元になる。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from db.schema import ConfirmStatus

ColumnType = Literal["integer", "number", "boolean", "string", "stamp", "json", "confirm", "id_list"]


class ColumnMeta(BaseModel):
    key: str
    label: str
    type: ColumnType
    nullable: bool
    required: bool
    # 長い本文の列か(フォームでは大きな textarea)
    section: bool = False
    choices: list[str] | None = None
    # 他のテーブルの id を指すなら、そのテーブル名
    references: str | None = None
    readonly: bool = False
    # 足すときにだけ渡せる欄(人物の place_id など)
    create_only: bool = False
    comment: str | None = None


class ChildListMeta(BaseModel):
    name: str
    label: str
    columns: list[ColumnMeta]


class TableMeta(BaseModel):
    name: str
    label: str
    label_column: str | None
    columns: list[ColumnMeta]
    child_lists: list[ChildListMeta]
    reviewable: bool
    count: int


class TablesResponse(BaseModel):
    tables: list[TableMeta]


class RecordList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[dict[str, Any]]
    # 参照先の名前。{列名: {id: 名前}}
    labels: dict[str, dict[int, str]] = Field(default_factory=dict)


class RecordResponse(BaseModel):
    record: dict[str, Any]
    label: str
    labels: dict[str, dict[int, str]] = Field(default_factory=dict)
    # 表示だけの関連情報(結んだ本文・居場所など)
    related: dict[str, Any] = Field(default_factory=dict)


class Option(BaseModel):
    id: int
    label: str


class OptionList(BaseModel):
    items: list[Option]


class ReviewTable(BaseModel):
    table: str
    label: str
    pending: int
    approved: int
    rejected: int


class ReviewSummary(BaseModel):
    tables: list[ReviewTable]


class ReviewNext(BaseModel):
    record: dict[str, Any] | None
    label: str | None
    remaining: int
    labels: dict[str, dict[int, str]] = Field(default_factory=dict)
    related: dict[str, Any] = Field(default_factory=dict)


class Decision(BaseModel):
    decision: ConfirmStatus
    # 承認・非承認と同時に直す欄
    changes: dict[str, Any] = Field(default_factory=dict)


class Health(BaseModel):
    world_dir: str
    db_path: str


class Created(BaseModel):
    id: int
