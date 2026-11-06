#!/usr/bin/env python3
"""API の入出力の形。OpenAPI に出て、フロント(`gui/web`)の型(`lib/openapi.d.ts`)の元になる。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from data_access_logic.character.relation_graph import RelationGraph
from data_access_logic.map.collect import PlanetMap

ColumnType = Literal["integer", "number", "boolean", "string", "stamp", "json", "id_list"]
# 参照先の名前。{列名: {id: 名前}}
Labels = dict[str, dict[int, str]]


class ColumnMeta(BaseModel):
    key: str
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
    # 子の行を持つテーブル
    table: str
    columns: list[ColumnMeta]
    # 子の一覧の仕様(`db/schema.py` の relationship の doc)
    comment: str | None = None
    # GUI での見せ方。"table"(既定): 素朴な編集可能な表。
    # "periodic": 期間(start・end)ごとの値を、期間を列にした読み取り専用の表 + モーダル編集で出す
    # (人物のパラメータ・居場所)。"flow": 本文の下に続けて、上から下へ流れる読み取り専用の札 + モーダル編集で
    # 出す(アイデアの呼び名。detail の注釈が長くなりがちなので、期間を列にする表よりこちらが読みやすい)
    display: ChildListDisplay = "table"
    # 行ごとに知る相手(`knowers`。`data_access_logic/knowers.py` の `KnowerRow` の配列)を、人物を選んで足す欄を出すか
    knowers: bool = False


class TableMeta(BaseModel):
    name: str
    label_column: str | None
    columns: list[ColumnMeta]
    child_lists: list[ChildListMeta]
    # 一覧の既定の並び
    sort: str = "id"
    order: Literal["asc", "desc"] = "desc"


class TablesResponse(BaseModel):
    """画面が持つ表の情報(`gui/web/lib/tables.json`。`gui/api/dump_static.py` が書き出す)。API からは返さない"""

    tables: list[TableMeta]


class TableCounts(BaseModel):
    # 表の名前ごとの行の数
    counts: dict[str, int]


class RecordList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[dict[str, Any]]
    labels: Labels = Field(default_factory=dict)


class RecordResponse(BaseModel):
    record: dict[str, Any]
    label: str
    labels: Labels = Field(default_factory=dict)
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
    # 人物 id をキーに、一番新しく設定された居場所(location の id。時刻を渡せばその時刻の居場所)。居場所を持たない人物は出ない
    locations: dict[int, int]


class LocationCharactersResponse(BaseModel):
    character_ids: list[int]


class TimelineResponse(BaseModel):
    # 一覧(`RecordList`)の一行と同じ形
    items: list[dict[str, Any]]
    labels: Labels = Field(default_factory=dict)


class OverviewEpisode(BaseModel):
    # 画面の型で欄が省けない(undefined にならない)よう、見取り図の応答の欄には既定値を付けない
    id: int
    title: str | None
    start: str
    end: str | None
    story_id: int
    story_name: str | None
    # 選んだ章(とその子孫)の話か。false は同じ期間の兄弟の作品(外伝など)の話
    in_story: bool


class OverviewSize(BaseModel):
    """出来事の大きさ。当事者の数と、人物モードの一手が足した行(居場所の移動・場所・現れた人物・事柄)を同じ重みで足す。"""

    people: int
    moves: int
    locations: int
    new_characters: int
    ideas: int
    total: int


class OverviewEvent(BaseModel):
    id: int
    name: str
    start: str
    end: str | None
    parent_event_id: int | None
    location_name: str | None
    origin: str
    hidden: bool
    text: str
    character_ids: list[int]
    # 人物モードの一手で足した出来事なら、その展開と動いた人物・巻きこんだ相手
    expansion_id: int | None
    actor_id: int | None
    invited_ids: list[int]
    expansion_summary: str | None
    expansion_prompt: str | None
    size: OverviewSize


class OverviewCharacter(BaseModel):
    id: int
    name: str | None
    main_character: bool
    # 選んだ章の話の登場人物(名前だけ出る人物は含めない)か
    in_cast: bool
    # 期間の終わりの影響力(主要人物は下限をかけた値)
    influence: str


class OverviewRelation(BaseModel):
    id: int
    character_1_id: int
    character_2_id: int
    relation: str
    start: str | None
    end: str | None


class OverviewResponse(BaseModel):
    story_id: int
    story_name: str | None
    # 章の話の始まりから終わりまでに、前後の余白を足した期間
    since: str
    until: str
    episodes: list[OverviewEpisode]
    events: list[OverviewEvent]
    characters: list[OverviewCharacter]
    relations: list[OverviewRelation]


class Health(BaseModel):
    dialect: str


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
    """画面が持つ入口の一覧(`gui/web/lib/entrances.json`。`gui/api/dump_static.py` が書き出す)。API からは返さない"""

    entrances: list[EntranceMeta]


class RunRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    entrance: str
    result: Any = None


class BatchRequest(BaseModel):
    # 問い合わせまで含めたパス(`/api/tables/story/records?limit=500`)。GET でだけ回す
    paths: list[str] = Field(min_length=1, max_length=20)


class BatchItem(BaseModel):
    status: int
    body: Any = None


class BatchResponse(BaseModel):
    responses: list[BatchItem]
