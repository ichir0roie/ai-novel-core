#!/usr/bin/env python3
"""データ編集 GUI の API。世界リポジトリのルートから次で起動する(`DEM_WORLD_DIR` / `PYTHONPATH` は他と同じ)。

    .venv/bin/python -m uvicorn gui.api.app:app --port 8765 --reload
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import OperationalError, StatementError
from sqlalchemy.orm import Session

from data_access_logic.character.latest_places import latest_place_ids
from data_access_logic.character.relation_graph import relation_graph
from data_access_logic.entrypoint import UnknownRecordError
from data_access_logic.logs import configure_logging
from data_access_logic.map.category import CATEGORIES, CATEGORY_COLORS, SHAPE_OPACITY
from data_access_logic.map.collect import planet_maps
from data_access_logic.map.geometry import BEARINGS
from data_access_logic.map.render_svg import COLORS, render_svg
from db.schema import DB_PATH, WORLD_DIR, get_env_session
from gui.api import generate, interface, meta, records, review
from gui.api.claude_env import ClaudeCommandForbidden, in_claude_code, require_claude_code
from gui.api.jobs import runner
from gui.api.models import (
    CharacterLocationsResponse, Created, Decision, EntranceList, EntranceMeta, GenerateRequest, Health, JobInfo,
    JobList, MapsResponse, OptionList, RecordList, RecordResponse, RelationsResponse, ReviewNext, ReviewSummary,
    RunRequest, RunResult, TablesResponse,
)
from gui.api.tables import spec_of

configure_logging()

app = FastAPI(title="ai-novel-core GUI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"], allow_headers=["*"],
)


def session_dep() -> Iterator[Session]:
    with get_env_session() as s:
        yield s


@app.exception_handler(KeyError)
async def _unknown_table(_request: Request, error: KeyError):
    return JSONResponse(status_code=404, content={"detail": str(error.args[0]) if error.args else "not found"})


@app.exception_handler(UnknownRecordError)
async def _unknown_record(_request: Request, error: UnknownRecordError):
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(ClaudeCommandForbidden)
async def _claude_forbidden(_request: Request, error: ClaudeCommandForbidden):
    return JSONResponse(status_code=403, content={"detail": str(error)})


@app.exception_handler(ValueError)
async def _bad_value(_request: Request, error: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(error)})


@app.exception_handler(StatementError)
async def _bad_bound_value(_request: Request, error: StatementError):
    # 列の型(Stamp・confirmed)が bind で弾いた値。SQLAlchemy が ValueError を包んで投げる
    if isinstance(error.orig, ValueError):
        return JSONResponse(status_code=400, content={"detail": str(error.orig)})
    return JSONResponse(status_code=500, content={"detail": str(error)})


@app.exception_handler(OperationalError)
async def _db_busy(_request: Request, error: OperationalError):
    # 他のセッションが書き込み中。少し待って再試行してもらう
    status = 503 if "locked" in str(error) else 500
    return JSONResponse(status_code=status, content={"detail": str(error.orig or error)})


@app.get("/api/health", response_model=Health)
def health() -> Health:
    return Health(world_dir=WORLD_DIR, db_path=DB_PATH)


@app.get("/api/tables", response_model=TablesResponse)
def tables(s: Session = Depends(session_dep)) -> TablesResponse:
    return TablesResponse(tables=meta.all_tables(s), claude_available=in_claude_code())


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


@app.post("/api/tables/{table}/generate/{generator}", response_model=JobInfo, status_code=202)
def generate_record(table: str, generator: str, request: GenerateRequest) -> JobInfo:
    """「AI で作成」。欄の値(下書き)を核に AI が全欄を組み立て直して行を足す。
    claude を叩くので Claude Code の環境でだけ、裏の job として走る。結果(足した行)は `/api/jobs/{id}` で引く"""
    spec = generate.generator_of(spec_of(table).name, generator)
    entrance = interface.entrance_of(spec.entrance)
    require_claude_code(entrance.id)
    args = generate.build_args(spec, request.draft, request.args)
    arguments = interface.prepare(entrance, args)
    job = runner.submit(entrance.id, args, lambda: interface.call(entrance, arguments))
    return JobInfo.model_validate(job)


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


@app.get("/api/review", response_model=ReviewSummary)
def review_summary(s: Session = Depends(session_dep)) -> ReviewSummary:
    return review.summary(s)


@app.get("/api/review/{table}/next", response_model=ReviewNext)
def review_next(table: str, after: int = Query(0, ge=0), s: Session = Depends(session_dep)) -> ReviewNext:
    return review.next_pending(s, review.review_spec(table), after=after)


@app.post("/api/review/{table}/{record_id}", response_model=RecordResponse)
def review_decide(table: str, record_id: int, decision: Decision,
                  s: Session = Depends(session_dep)) -> RecordResponse:
    spec = review.review_spec(table)
    with s.begin():
        record = review.decide(s, spec, record_id, decision.decision, decision.changes)
    return records.response_of(s, spec, record)


@app.get("/api/interface", response_model=EntranceList)
def list_entrances() -> EntranceList:
    """入口の一覧。`claude` が立つものは Claude Code の環境でだけ、裏の job として走る"""
    return EntranceList(entrances=[EntranceMeta.model_validate(entrance) for entrance in interface.ENTRANCES.values()],
                        claude_available=in_claude_code())


@app.post("/api/interface/{entrance_id}", response_model=RunResult | JobInfo)
def run_entrance(entrance_id: str, request: RunRequest, response: Response) -> RunResult | JobInfo:
    """入口を呼ぶ。`claude` を叩く入口(と `background` を立てた呼び出し)は job の id を 202 で返し、結果は `/api/jobs/{id}` で引く"""
    entrance = interface.entrance_of(entrance_id)
    if entrance.claude:
        require_claude_code(entrance.id)
    arguments = interface.prepare(entrance, request.args)
    if entrance.claude or request.background:
        job = runner.submit(entrance.id, request.args, lambda: interface.call(entrance, arguments))
        response.status_code = 202
        return JobInfo.model_validate(job)
    return RunResult(entrance=entrance.id, result=interface.call(entrance, arguments))


@app.get("/api/jobs", response_model=JobList)
def list_jobs() -> JobList:
    return JobList(jobs=[JobInfo.model_validate(job) for job in runner.list()])


@app.get("/api/jobs/{job_id}", response_model=JobInfo)
def get_job(job_id: str) -> JobInfo:
    job = runner.get(job_id)
    if job is None:
        raise UnknownRecordError(f"job が無い: {job_id}")
    return JobInfo.model_validate(job)


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


@app.get("/api/relations", response_model=RelationsResponse)
def relations(s: Session = Depends(session_dep)) -> RelationsResponse:
    """人物相関図の元データ。画面(`/relations`)が描く"""
    graph = relation_graph(s)
    return RelationsResponse(characters=graph.characters, relations=graph.relations, colors=list(COLORS))


@app.get("/api/character_locations", response_model=CharacterLocationsResponse)
def character_locations(s: Session = Depends(session_dep)) -> CharacterLocationsResponse:
    """人物ごとの居場所。人物一覧のツリー表示(`/tables/character?view=tree`)が場所ごとに束ねるのに使う"""
    return CharacterLocationsResponse(locations=latest_place_ids(s))


_ = Created  # OpenAPI に出す型として残す
