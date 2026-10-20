#!/usr/bin/env python3
"""ミームの db の段(`data_access_logic/step.py`)。流れ(`data_access_logic/flows/`)が、手元では自分のセッションで、web のセッションでは API 越しに呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.meme import extractor
from data_access_logic.meme.models import AntiMeme, MemeCategory, MemeDraft
from data_access_logic.source_text import SourceRows, SourceText
from data_access_logic.step import db_step


class MemesForm(BaseModel):
    memes: list[MemeDraft]


class CategoriesForm(BaseModel):
    categories: list[MemeCategory]


class AntiMemesForm(BaseModel):
    antis: list[AntiMeme]


@db_step
def sources(s: Session, form: SourceRows) -> list[SourceText]:
    return extractor.sources_of(s, form.rows)


@db_step
def meme_texts(s: Session) -> list[str]:
    return extractor.meme_texts(s)


@db_step
def save_memes(s: Session, form: MemesForm) -> int:
    return extractor.save_memes(s, form.memes)


@db_step
def unpaired_sources(s: Session) -> list[SourceText]:
    return extractor.unpaired_sources(s)


@db_step
def save_anti_memes(s: Session, form: AntiMemesForm) -> int:
    return extractor.save_anti_memes(s, form.antis)


@db_step
def unclassified_sources(s: Session) -> list[SourceText]:
    return extractor.unclassified_sources(s)


@db_step
def save_categories(s: Session, form: CategoriesForm) -> int:
    return extractor.save_categories(s, form.categories)
