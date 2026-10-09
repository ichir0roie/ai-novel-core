#!/usr/bin/env python3
"""データ編集 GUI の API。リポジトリのルートから次で起動する(`DEM_DATABASE_URL` などは他の python と同じ)。

    .venv/bin/python -m uvicorn gui.api.app:app --port 8765 --reload
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
from collections.abc import Iterator
from typing import Any

import httpx
from fastapi import Body, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import OperationalError, StatementError
from sqlalchemy.orm import Session

from data_access_logic import step
from data_access_logic.character.latest_locations import latest_location_ids
from data_access_logic.character.location_characters import location_character_ids
from data_access_logic.character.relation_graph import relation_graph
from data_access_logic.entrypoint import UnknownRecordError
from data_access_logic.episode import reading as episode_reading
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.episode_session.read_session_since import ReadSessionSince
from data_access_logic.episode_session.record import SessionSince
from data_access_logic.logs import configure_logging
from data_access_logic.map.category import CATEGORIES, CATEGORY_COLORS, SHAPE_OPACITY
from data_access_logic.map.collect import planet_maps
from data_access_logic.map.geometry import BEARINGS
from data_access_logic.map.render_svg import COLORS, render_svg
from data_access_logic.map.story_route import StoryRoute, story_route
from db.schema import engine, get_env_session
from db.stamp import Stamp
from gui.api import interface, meta, records, timeline
from gui.api.models import (
    BatchItem, BatchRequest, BatchResponse, CharacterLocationsResponse, Created, EntranceList, EntranceMeta, Health, MapsResponse, OptionList, LocationCharactersResponse, RecordList, RecordResponse, RelationsResponse,
    RunRequest, RunResult, TablesResponse, TimelineResponse,
)
from gui.api.tables import spec_of

logger = logging.getLogger(__name__)
configure_logging()
# `/api/batch` の中の要求は合言葉の確かめのところで一つずつ出すので、httpx の行は重ねない
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title="ai-novel-core GUI API", version="0.1.0")

# 公開の URL(Lambda の関数 URL など)に置くときの合言葉。呼ぶ側ごとに `名前=鍵` をカンマで区切って持つ(例: gui=…,web=…)。
# 呼ぶ側ごとに分けるのは、漏れる危険の高い web のセッションの鍵を、画面の鍵を止めずに替えたり外したりするため。
# 画面の Next.js のサーバー(`gui/web/app/api`)や web のセッションが付けて流す。空ならローカル向けとして確かめない
API_KEY_HEADER = "x-novel-api-key"


def _parse_api_keys(raw: str) -> dict[str, str]:
    keys: dict[str, str] = {}
    for entry in filter(None, (entry.strip() for entry in raw.split(","))):
        name, _, key = (part.strip() for part in entry.partition("="))
        if not name or not key:
            raise ValueError("NOVEL_API_KEYS は `名前=鍵` をカンマで区切って書く")
        keys[name] = key
    return keys


_API_KEYS = _parse_api_keys(os.environ.get("NOVEL_API_KEYS", ""))
# 合言葉なしで通すパス。Lambda Web Adapter の起動確認が叩く
_PUBLIC_PATHS = {"/api/ping"}


@app.middleware("http")
async def _require_api_key(request: Request, call_next):
    if _API_KEYS and request.url.path not in _PUBLIC_PATHS:
        given = request.headers.get(API_KEY_HEADER, "").encode()
        caller = next((name for name, key in _API_KEYS.items() if hmac.compare_digest(given, key.encode())), None)
        if caller is None:
            return JSONResponse(status_code=401, content={"detail": f"{API_KEY_HEADER} が無いか違う"})
        # おかしな書き込みがあったときに、画面からか web のセッションからかを切り分けられるよう、鍵の名前だけを出す
        logger.info(f"{caller}: {request.method} {request.url.path}")
    return await call_next(request)


def session_dep() -> Iterator[Session]:
    with get_env_session() as s:
        yield s


@app.exception_handler(UnknownRecordError)
async def _unknown_record(_request: Request, error: UnknownRecordError):
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(interface.ClaudeEntranceForbidden)
async def _claude_forbidden(_request: Request, error: interface.ClaudeEntranceForbidden):
    return JSONResponse(status_code=403, content={"detail": str(error)})


@app.exception_handler(ValueError)
async def _bad_value(_request: Request, error: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(error)})


@app.exception_handler(StatementError)
async def _bad_bound_value(_request: Request, error: StatementError):
    # 列の型(Stamp)が bind で弾いた値。SQLAlchemy が ValueError を包んで投げる
    if isinstance(error.orig, ValueError):
        return JSONResponse(status_code=400, content={"detail": str(error.orig)})
    return JSONResponse(status_code=500, content={"detail": str(error)})


# ロック待ちの打ち切り・デッドロック・直列化の失敗。少し待って再試行してもらう
_DB_BUSY_SQLSTATES = {"55P03", "40P01", "40001"}


@app.exception_handler(OperationalError)
async def _db_busy(_request: Request, error: OperationalError):
    if getattr(error.orig, "sqlstate", None) in _DB_BUSY_SQLSTATES:
        return JSONResponse(status_code=503, content={"detail": "db is busy; retry later"})
    # 接続先などの db の内部を呼ぶ側へ出さない
    logger.error("db の操作に失敗した", exc_info=error)
    return JSONResponse(status_code=500, content={"detail": "db operation failed"})


@app.get("/api/ping")
def ping() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/health", response_model=Health)
def health() -> Health:
    return Health(dialect=engine.dialect.name)


@app.get("/api/tables", response_model=TablesResponse)
def tables(s: Session = Depends(session_dep)) -> TablesResponse:
    return TablesResponse(tables=meta.all_tables(s))


@app.get("/api/tables/{table}/records", response_model=RecordList)
def list_records(table: str, request: Request, q: str | None = None,
                 limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                 sort: str | None = None, order: str | None = Query(None, pattern="^(asc|desc)$"),
                 s: Session = Depends(session_dep)) -> RecordList:
    spec = spec_of(table)
    reserved = {"q", "limit", "offset", "sort", "order"}
    filters = {key: value for key, value in request.query_params.items() if key not in reserved}
    return records.list_records(s, spec, q=q, limit=limit, offset=offset,
                                sort=sort or spec.sort, order=order or spec.order, filters=filters)


@app.get("/api/tables/{table}/options", response_model=OptionList)
def list_options(table: str, q: str | None = None, limit: int = Query(200, ge=1, le=2000),
                 ids: list[int] | None = Query(None),
                 s: Session = Depends(session_dep)) -> OptionList:
    return OptionList(items=records.options(s, spec_of(table), q=q, limit=limit, ids=ids))


@app.post("/api/tables/{table}/records", response_model=RecordResponse, status_code=201)
def create_record(table: str, data: dict[str, Any], s: Session = Depends(session_dep)) -> RecordResponse:
    spec = spec_of(table)
    with s.begin():
        record = records.create_record(s, spec, data)
    return records.response_of(s, spec, record)


@app.get("/api/tables/{table}/records/{record_id}", response_model=RecordResponse)
def get_record(table: str, record_id: int, s: Session = Depends(session_dep)) -> RecordResponse:
    return records.get_record(s, spec_of(table), record_id)


@app.patch("/api/tables/{table}/records/{record_id}", response_model=RecordResponse)
def update_record(table: str, record_id: int, data: dict[str, Any],
                  s: Session = Depends(session_dep)) -> RecordResponse:
    spec = spec_of(table)
    with s.begin():
        record = records.update_record(s, spec, record_id, data)
    return records.response_of(s, spec, record)


@app.get("/api/interface", response_model=EntranceList)
def list_entrances() -> EntranceList:
    """db だけの入口の一覧。claude を叩く入口は出さない(Claude のセッションが自分で呼ぶ)"""
    return EntranceList(entrances=[EntranceMeta.model_validate(entrance) for entrance in interface.ENTRANCES.values()
                                   if not entrance.claude])


@app.post("/api/interface/{entrance_id}", response_model=RunResult)
def run_entrance(entrance_id: str, request: RunRequest) -> RunResult:
    entrance = interface.db_entrance_of(entrance_id)
    return RunResult(entrance=entrance.id, result=interface.call(entrance, interface.prepare(entrance, request.args)))


@app.post("/api/steps/{step_id}")
def run_step(step_id: str, body: Any = Body(None)) -> Any:
    """db の段(`data_access_logic/<領域>/steps.py`)を一つのトランザクションで回す。web のセッション(`web_session/`)が、
    流れと AI を自分で持ったまま db に触る所だけを頼む"""
    return step.run_json(step_id, body)


@app.post("/api/batch", response_model=BatchResponse)
async def batch(body: BatchRequest, request: Request) -> BatchResponse:
    """同じ時に出た GET をまとめて回す。Lambda は一つの実行環境で一つの要求しか受けないので、画面が並べて呼ぶと
    その数だけ実行環境が起き、それぞれがコールドスタートを待つ"""
    for path in body.paths:
        if not path.startswith("/api/") or path.startswith("/api/batch"):
            raise ValueError(f"まとめて回せないパス: {path}")
    # 一つずつの要求も合言葉の確かめとログを通るよう、受けた鍵をそのまま付ける
    key = request.headers.get(API_KEY_HEADER)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://batch",
                                 headers={API_KEY_HEADER: key} if key else None) as client:
        responses = await asyncio.gather(*(client.get(path) for path in body.paths))
    return BatchResponse(responses=[
        BatchItem(status=response.status_code,
                  body=response.json() if response.headers.get("content-type") == "application/json"
                  else {"detail": response.text})
        for response in responses])


@app.get("/api/maps", response_model=MapsResponse)
def maps(s: Session = Depends(session_dep)) -> MapsResponse:
    """星ごとの地図の元データ。画面(`/maps`)が場所の座標・領域から描く"""
    return MapsResponse(planets=planet_maps(s), categories=list(CATEGORIES),
                        category_colors=dict(CATEGORY_COLORS), shape_opacity=dict(SHAPE_OPACITY),
                        bearings=list(BEARINGS))


@app.get("/api/maps/{planet_id}.svg")
def map_svg(planet_id: int, s: Session = Depends(session_dep)) -> Response:
    for planet_map in planet_maps(s):
        if planet_map.planet.id == planet_id:
            return Response(render_svg(planet_map.planet, planet_map.points, planet_map.shapes), media_type="image/svg+xml")
    raise UnknownRecordError(f"id={planet_id} の星に地図が無い(座標を持つ場所が無いか、星でない)")


@app.get("/api/story_route", response_model=StoryRoute)
def get_story_route(story_id: int, s: Session = Depends(session_dep)) -> StoryRoute:
    """作品の話を順に並べ、それぞれを地図に置く位置。地図(`/maps?story=`)が場所の移り変わりを描く"""
    return story_route(s, story_id)


@app.get("/api/relations", response_model=RelationsResponse)
def relations(s: Session = Depends(session_dep)) -> RelationsResponse:
    """人物相関図の元データ。画面(`/relations`)が描く"""
    graph = relation_graph(s)
    return RelationsResponse(characters=graph.characters, relations=graph.relations, colors=list(COLORS))


@app.get("/api/character_locations", response_model=CharacterLocationsResponse)
def character_locations(s: Session = Depends(session_dep)) -> CharacterLocationsResponse:
    """人物ごとの居場所。人物一覧のツリー表示(`/tables/character?view=tree`)が場所ごとに束ねるのに使う"""
    return CharacterLocationsResponse(locations=latest_location_ids(s))


@app.get("/api/location_characters", response_model=LocationCharactersResponse)
def location_characters(location_id: int, time: str, s: Session = Depends(session_dep)) -> LocationCharactersResponse:
    """`time` に `location_id` の場所か、その上位の場所にいる人物。話の登場人物の候補を、フォームの場所・時刻で絞るのに使う"""
    at = Stamp.parse(time)
    if at is None:
        raise ValueError("時刻が空")
    return LocationCharactersResponse(character_ids=location_character_ids(s, location_id, at))


@app.get("/api/timeline", response_model=TimelineResponse)
def get_timeline(story_id: int | None = None, s: Session = Depends(session_dep)) -> TimelineResponse:
    """全期間の話。画面(`/timeline`)が時刻の軸に並べる"""
    return timeline.timeline(s, story_id=story_id)


@app.get("/api/previous_episode", response_model=EpisodeRecord | None)
def previous_episode(story_id: int, before: str | None = None,
                     s: Session = Depends(session_dep)) -> EpisodeRecord | None:
    """作品の中で `before`(時刻)より前の一番後ろの話。`before` が無ければ作品の最後の話。
    話を新しく足す画面が、場所・視点・登場人物の初期値を写すのに使う"""
    return episode_reading.previous_episode(s, story_id, before)


@app.get("/api/episode_neighbors", response_model=episode_reading.EpisodeNeighbors)
def episode_neighbors(episode_id: int, s: Session = Depends(session_dep)) -> episode_reading.EpisodeNeighbors:
    """同じ作品の時刻の順で前後の話。話の画面のタイトルの横の移動ボタンが使う"""
    return episode_reading.neighbor_episodes(s, episode_id)


@app.get("/api/episode_session", response_model=SessionSince)
def episode_session(episode_id: int, after_id: int | None = None, s: Session = Depends(session_dep)) -> SessionSince:
    """話のセッションの行のうち `after_id` より新しい行と、行の総数。画面(`/episode_session`)が毎秒引いて増分を足す"""
    return ReadSessionSince(episode_id, after_id).execute(s)


_ = Created  # OpenAPI に出す型として残す
