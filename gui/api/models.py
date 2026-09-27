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


class EntranceParam(BaseModel):
    name: str
    required: bool
    default: Any = None
    annotation: str = ""


class EntranceMeta(BaseModel):
    id: str
    area: str
    name: str
    doc: str
    params: list[EntranceParam]
    # claude コマンドを叩く(Claude Code の環境でだけ、裏の job として走る)
    claude: bool
    writes: bool


class EntranceList(BaseModel):
    entrances: list[EntranceMeta]
    # この API が Claude Code の環境で起きているか(false なら claude=true の入口は 403)
    claude_available: bool


class RunRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)
    # true なら claude を叩かない入口も裏の job で走らせる
    background: bool = False


class RunResult(BaseModel):
    entrance: str
    result: Any = None


class JobInfo(BaseModel):
    id: str
    entrance: str
    args: dict[str, Any]
    status: Literal["queued", "running", "done", "failed"]
    result: Any = None
    error: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class JobList(BaseModel):
    jobs: list[JobInfo]
