#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import Select, select

from db.schema import ConfirmStatus, Meme


def unseeded_select(model) -> Select:
    return select(model).where(model.meme_seeded.is_(False)).order_by(model.id)


def unconfirmed_memes_select() -> Select:
    """まだ確かめていない候補(`confirmed=未確認`)。退けた(非承認)ものは含めない。"""
    return select(Meme).where(Meme.confirmed == ConfirmStatus.PENDING).order_by(Meme.id)
