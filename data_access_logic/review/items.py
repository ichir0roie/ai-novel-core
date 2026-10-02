#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.label import label_of
from data_access_logic.query import review_query
from db.schema import Base, Story


class PendingReview(BaseModel):
    # 同じものを二度タスクにしないための印
    key: str
    kind: str
    title: str
    detail: str


def gui_path(record: Base) -> str:
    """GUI(`gui/`)で開く場所"""
    return f"gui: /tables/{type(record).__tablename__}/{record.id}"


def unsynced_episode_items(s: Session) -> list[PendingReview]:
    items = []
    for episode in s.scalars(review_query.written_unsynced_episodes_select()).all():
        story = s.get(Story, episode.story_id)
        story_name = story.name if story else f"作品 id={episode.story_id}"
        items.append(PendingReview(
            key=f"episode:{episode.id}",
            kind="未同期の話",
            title=f"{story_name}「{episode.title}」を世界観へ反映して synced を立てる",
            detail="\n".join([
                "本文の出来事・行動を台帳へ戻す。戻すまで、この作品の次の話が書けない。",
                gui_path(episode),
                f"済んだら: SetEpisodeSynced({episode.id})",
            ]),
        ))
    return items


def todo_items(s: Session) -> list[PendingReview]:
    items = []
    for model in review_query.text_models():
        for record in s.scalars(review_query.todo_select(model)).all():
            lines = [line.strip() for name in model.TEXT_COLUMNS
                     for line in (getattr(record, name) or "").splitlines()
                     if review_query.TODO_MARK in line]
            items.append(PendingReview(
                key=f"todo:{model.__tablename__}:{record.id}",
                kind="TODO",
                title=f"TODO を片付ける: {model.__tablename__}「{label_of(model, record)}」",
                detail="\n".join([*lines, gui_path(record)]),
            ))
    return items
