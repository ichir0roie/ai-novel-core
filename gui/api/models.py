#!/usr/bin/env python3
"""API の入出力の形。OpenAPI に出て、フロント(`gui/web`)の型(`lib/openapi.d.ts`)の元になる。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from data_access_logic.character.relation_graph import RelationGraph
from data_access_logic.map.collect import PlanetMap

ColumnType = Literal["integer", "number", "boolean", "string", "stamp", "json", "id_list"]


class ColumnMeta(BaseModel):
    key: str
    label: str
    type: ColumnType
    nullable: bool
    required: bool
    # 長い本文の列か(フォームでは大きな textarea)
    section: bool = False
    # section の欄をマークダウンのプレビュー付きにするか。false なら純粋なテキストとして扱う
    markdown: bool = True
    # section のうち、本文と並べず左側の欄の一番下に高さを決めたスクロール欄で置くか(話のプロットなど、
    # 本文とは別に参照するだけの短いメモ)
    side: bool = False
    choices: list[str] | None = None
    # choices のうち、空欄のときに実際に使われる値(プルダウンにその選択肢だと分かるよう "(default)" を添える)
    default: str | None = None
    # 他のテーブルの id を指すなら、そのテーブル名
    references: str | None = None
    readonly: bool = False
    # 足すときにだけ渡せる欄(人物の location_id など)
    create_only: bool = False
    comment: str | None = None


ChildListDisplay = Literal["table", "periodic", "flow"]


class ChildListMeta(BaseModel):
    name: str
    label: str
    columns: list[ColumnMeta]
    # GUI での見せ方。"table"(既定): 素朴な編集可能な表(アイデアの notes など)。
    # "periodic": 期間(start・end)ごとの値を、期間を列にした読み取り専用の表 + モーダル編集で出す
    # (人物のパラメータ・居場所)。"flow": 本文の下に続けて、上から下へ流れる読み取り専用の札 + モーダル編集で
    # 出す(アイデアの呼び名。detail の注釈が長くなりがちなので、期間を列にする表よりこちらが読みやすい)
    display: ChildListDisplay = "table"


class TableMeta(BaseModel):
    name: str
    label: str
    label_column: str | None
    columns: list[ColumnMeta]
    child_lists: list[ChildListMeta]
    count: int
    # 一覧の既定の並び
    sort: str = "id"
    order: Literal["asc", "desc"] = "desc"


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
    # ツリー選択(場所・アイデアなど、自己参照で親子を持つテーブル)で親を辿るための列の値
    parent_id: int | None = None
    # 誕生(`Character.start`。人物だけ)。話の登場人物モーダルで、その話の時点の年齢を出すのに使う
    born: str | None = None


class OptionList(BaseModel):
    items: list[Option]


class MapsResponse(BaseModel):
    planets: list[PlanetMap]
    categories: list[str]
    category_colors: dict[str, str]
    shape_opacity: dict[str, float]
    # 方角の名(北から時計回りに 16 方位)
    bearings: list[str]


class RelationsResponse(RelationGraph):
    # 種別ごとの色に使う並び
    colors: list[str]


class CharacterLocationsResponse(BaseModel):
    # 人物 id をキーに、一番新しく設定された居場所(location の id)。居場所を持たない人物は出ない
    locations: dict[int, int]


class LocationCharactersResponse(BaseModel):
    character_ids: list[int]


class TimelineResponse(BaseModel):
    # 一覧(`RecordList`)の一行と同じ形
    items: list[dict[str, Any]]
    labels: dict[str, dict[int, str]] = Field(default_factory=dict)


class Health(BaseModel):
    dialect: str


class Created(BaseModel):
    id: int


class EntranceParam(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    required: bool
    default: Any = None
    annotation: str = ""


class EntranceMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    area: str
    name: str
    doc: str
    params: list[EntranceParam]
    writes: bool


class EntranceList(BaseModel):
    entrances: list[EntranceMeta]


class RunRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    entrance: str
    result: Any = None


