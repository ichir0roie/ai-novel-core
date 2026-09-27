#!/usr/bin/env python3
"""データ編集 GUI の API。世界リポジトリのルートから次で起動する(`DEM_WORLD_DIR` / `PYTHONPATH` は他と同じ)。

    .venv/bin/python -m uvicorn gui.api.app:app --port 8765 --reload
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.exc import OperationalError, StatementError
from sqlalchemy.orm import Session

from ai.claude_code.interface._base import UnknownRecordError
from db.schema import DB_PATH, WORLD_DIR, get_env_session
from gui.api import meta, records, review
from gui.api.models import (
    Created, Decision, Health, OptionList, RecordList, RecordResponse, ReviewNext, ReviewSummary,
    TablesResponse,
)
from gui.api.tables import spec_of
from tool.map.collect import collect_planets
from tool.map.render_html import render_html as render_map_html
from tool.map.render_svg import render_svg
from tool.relation.collect import collect_relations
from tool.relation.render_html import render_html as render_relation_html

app = FastAPI(title="ai-novel-core GUI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"], allow_headers=["*"],
)


def session_dep():
    with get_env_session() as session:
        yield session


@app.exception_handler(KeyError)
async def _unknown_table(_request: Request, error: KeyError):
    return JSONResponse(status_code=404, content={"detail": str(error.args[0]) if error.args else "not found"})


@app.exception_handler(UnknownRecordError)
async def _unknown_record(_request: Request, error: UnknownRecordError):
    return JSONResponse(status_code=404, content={"detail": str(error)})


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
def tables(session: Session = Depends(session_dep)) -> TablesResponse:
    return TablesResponse(tables=meta.all_tables(session))


@app.get("/api/tables/{table}/records", response_model=RecordList)
def list_records(table: str, request: Request, q: str | None = None,
                 limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                 order: str = Query("asc", pattern="^(asc|desc)$"),
                 session: Session = Depends(session_dep)) -> RecordList:
    spec = spec_of(table)
    reserved = {"q", "limit", "offset", "order"}
    filters = {key: value for key, value in request.query_params.items() if key not in reserved}
    return records.list_records(session, spec, q=q, limit=limit, offset=offset, order=order, filters=filters)


@app.get("/api/tables/{table}/options", response_model=OptionList)
def list_options(table: str, q: str | None = None, limit: int = Query(200, ge=1, le=2000),
                 ids: list[int] | None = Query(None),
                 session: Session = Depends(session_dep)) -> OptionList:
    return OptionList(items=records.options(session, spec_of(table), q=q, limit=limit, ids=ids))


@app.post("/api/tables/{table}/records", response_model=RecordResponse, status_code=201)
def create_record(table: str, data: dict[str, Any], session: Session = Depends(session_dep)) -> RecordResponse:
    spec = spec_of(table)
    with session.begin():
        record_id = records.create_record(session, spec, data)
    return records.get_record(session, spec, record_id)


@app.get("/api/tables/{table}/records/{record_id}", response_model=RecordResponse)
def get_record(table: str, record_id: int, session: Session = Depends(session_dep)) -> RecordResponse:
    return records.get_record(session, spec_of(table), record_id)


@app.patch("/api/tables/{table}/records/{record_id}", response_model=RecordResponse)
def update_record(table: str, record_id: int, data: dict[str, Any],
                  session: Session = Depends(session_dep)) -> RecordResponse:
    spec = spec_of(table)
    with session.begin():
        records.update_record(session, spec, record_id, data)
    return records.get_record(session, spec, record_id)


@app.get("/api/review", response_model=ReviewSummary)
def review_summary(session: Session = Depends(session_dep)) -> ReviewSummary:
    return review.summary(session)


@app.get("/api/review/{table}/next", response_model=ReviewNext)
def review_next(table: str, after: int = Query(0, ge=0), session: Session = Depends(session_dep)) -> ReviewNext:
    return review.next_pending(session, review.review_spec(table), after=after)


@app.post("/api/review/{table}/{record_id}", response_model=RecordResponse)
def review_decide(table: str, record_id: int, decision: Decision,
                  session: Session = Depends(session_dep)) -> RecordResponse:
    spec = review.review_spec(table)
    with session.begin():
        review.decide(session, spec, record_id, decision.decision, decision.changes)
    return records.get_record(session, spec, record_id)


@app.get("/api/maps", response_class=HTMLResponse)
def maps(session: Session = Depends(session_dep)) -> HTMLResponse:
    """星ごとの地図(html)。場所の座標・領域から描く"""
    return HTMLResponse(render_map_html(collect_planets(session)))


@app.get("/api/maps/{planet_id}.svg")
def map_svg(planet_id: int, session: Session = Depends(session_dep)) -> Response:
    for entry in collect_planets(session):
        if entry["planet"]["id"] == planet_id:
            return Response(render_svg(entry["planet"], entry["points"], entry["shapes"]), media_type="image/svg+xml")
    raise UnknownRecordError(f"id={planet_id} の星に地図が無い(座標を持つ場所が無いか、星でない)")


@app.get("/api/relations", response_class=HTMLResponse)
def relations(session: Session = Depends(session_dep)) -> HTMLResponse:
    """人物相関図(html)"""
    return HTMLResponse(render_relation_html(collect_relations(session)))


_ = Created  # OpenAPI に出す型として残す
