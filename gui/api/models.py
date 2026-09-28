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
    # section の欄をマークダウンのプレビュー付きにするか。false なら純粋なテキストとして扱う
    markdown: bool = True
    # section のうち、本文と並べず左側の欄の一番下に高さを決めたスクロール欄で置くか(話のキーテキストなど、
    # 本文とは別に参照するだけの短い種)
    side: bool = False
    choices: list[str] | None = None
    # choices のうち、空欄のときに実際に使われる値(プルダウンにその選択肢だと分かるよう "(default)" を添える)
    default: str | None = None
    # 他のテーブルの id を指すなら、そのテーブル名
    references: str | None = None
    readonly: bool = False
    # 足すときにだけ渡せる欄(人物の place_id など)
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


class GeneratorMeta(BaseModel):
    """「AI で作成」のボタン。欄の値(下書き)を核に AI が全欄を組み立て直して行を足す。"""
    key: str
    label: str
    # 呼ぶ入口(`/api/interface` の id)。claude を叩くので裏の job になる
    entrance: str
    # 足す画面(create)・直す画面(edit)・両方(both)のどこに出すか
    mode: Literal["create", "edit", "both"]
    # 直す画面では、この欄が空のときだけ出す(本文の無い話にだけ「本文を書く」を出すなど)
    when_empty: str | None = None
    # 直す画面では、この欄が空でないときだけ出す(本文のある話にだけ「推敲する」を出すなど)
    when_not_empty: str | None = None
    # 行の欄の外で受け取る指定(現在の時刻・登場人物など)
    params: list[ColumnMeta] = Field(default_factory=list)
    # true なら「AI で作成」の小さなボタン列(GeneratePanel)には出さず、専用の大きなパネル(RevisePanel)で出す
    panel: bool = False


class TableMeta(BaseModel):
    name: str
    label: str
    label_column: str | None
    columns: list[ColumnMeta]
    child_lists: list[ChildListMeta]
    reviewable: bool
    count: int
    generators: list[GeneratorMeta] = Field(default_factory=list)
    # 一覧の既定の並び
    sort: str = "id"
    order: Literal["asc", "desc"] = "desc"


class TablesResponse(BaseModel):
    tables: list[TableMeta]
    # この API が Claude Code の環境で起きているか(false なら「AI で作成」は 403)
    claude_available: bool = False


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


class Planet(BaseModel):
    id: int
    name: str | None
    area: float | None
    radius_km: float | None


class MapPlace(BaseModel):
    id: int
    name: str | None
    kind: str | None
    # 地図の色分け(`tool.map.category`)
    category: str
    parent_id: int | None
    parent_name: str | None
    parent_kind: str | None
    lon: float | None
    lat: float | None
    alt: float | None
    polygon: dict[str, Any] | None
    environment: str | None
    sample_region: str | None
    sample_culture: str | None
    sample_era: str | None
    start: str | None
    end: str | None
    link: str


class PlanetMap(BaseModel):
    planet: Planet
    # 経緯度を持つ場所
    points: list[MapPlace]
    # 輪郭(polygon)を持つ場所
    shapes: list[MapPlace]


class MapsResponse(BaseModel):
    planets: list[PlanetMap]
    categories: list[str]
    category_colors: dict[str, str]
    shape_opacity: dict[str, float]
    # 方角の名(北から時計回りに 16 方位)
    bearings: list[str]


class RelationCharacter(BaseModel):
    id: int
    name: str | None
    kind: str | None
    sex: str | None
    start: int | None
    end: int | None
    link: str


class Relation(BaseModel):
    id: int
    character_id_1: int
    character_id_2: int
    relation: str | None
    start: int | None
    end: int | None
    text: str


class RelationsResponse(BaseModel):
    characters: list[RelationCharacter]
    relations: list[Relation]
    # 種別ごとの色に使う並び
    colors: list[str]


class CharacterLocationsResponse(BaseModel):
    # 人物 id をキーに、一番新しく設定された居場所(location の id)。居場所を持たない人物は出ない
    locations: dict[int, int]


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


class GenerateRequest(BaseModel):
    # 欄の値(下書き)。空の欄は省いてよい
    draft: dict[str, Any] = Field(default_factory=dict)
    # `GeneratorMeta.params` の値
    args: dict[str, Any] = Field(default_factory=dict)


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
