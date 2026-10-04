#!/usr/bin/env python3
"""ミームの db の段(`data_access_logic/step.py`)。流れ(`data_access_logic/flows/`)が、手元では自分のセッションで、web のセッションでは API 越しに呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.meme import extractor
from data_access_logic.meme.models import MemeCategory, MemeDraft
from data_access_logic.source_text import SourceText
from data_access_logic.step import db_step


class MemesForm(BaseModel):
    memes: list[MemeDraft]
    # 抜き出し済みの印を付ける元
    sources: list[SourceText]


class CategoriesForm(BaseModel):
    categories: list[MemeCategory]


@db_step
def pending_sources(s: Session) -> list[SourceText]:
    return extractor.pending_sources(s)


@db_step
def meme_texts(s: Session) -> list[str]:
    return extractor.meme_texts(s)


@db_step
def save_memes(s: Session, form: MemesForm) -> int:
    return extractor.save_memes(s, form.memes, form.sources)


@db_step
def unclassified_sources(s: Session) -> list[SourceText]:
    return extractor.unclassified_sources(s)


@db_step
def save_categories(s: Session, form: CategoriesForm) -> int:
    return extractor.save_categories(s, form.categories)
