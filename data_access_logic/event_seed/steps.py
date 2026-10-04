#!/usr/bin/env python3
"""出来事の種の db の段(`data_access_logic/step.py`)。流れ(`data_access_logic/flows/`)が、手元では自分のセッションで、web のセッションでは API 越しに呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.event_seed import extractor
from data_access_logic.event_seed.models import SeedMerge, SeedPiles
from data_access_logic.source_text import SourceText
from data_access_logic.step import RowIds, db_step


class SeedsForm(BaseModel):
    seeds: list[str]
    # 抜き出し済みの印を付ける元
    sources: list[SourceText]


class MergesForm(BaseModel):
    merges: list[SeedMerge]


@db_step
def pending_sources(s: Session) -> list[SourceText]:
    return extractor.pending_sources(s)


@db_step
def save_seeds(s: Session, form: SeedsForm) -> int:
    return extractor.save_seeds(s, form.seeds, form.sources)


@db_step
def seed_piles(s: Session) -> SeedPiles | None:
    return extractor.seed_piles(s)


@db_step
def apply_merges(s: Session, form: MergesForm) -> None:
    extractor.apply_merges(s, form.merges)


@db_step
def settle_seeds(s: Session, form: RowIds) -> None:
    extractor.settle_seeds(s, form.ids)


@db_step
def seed_pool(s: Session) -> list[str]:
    return extractor.seed_pool(s)
