#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.idea.links import appearances
from data_access_logic.label import label_of
from data_access_logic.query import review_query
from db.schema import Base, Idea, Meme, Story


class PendingReview(BaseModel):
    # 同じものを二度タスクにしないための印
    key: str
    kind: str
    title: str
    detail: str


def gui_path(record: Base) -> str:
    """GUI(`gui/`)で開く場所"""
    return f"gui: /tables/{type(record).__tablename__}/{record.id}"


def _appearances(session: Session, idea: Idea) -> str:
    places = [f"{place.table}「{place.label}」(id={place.id})" for place in appearances(session, idea.id)]
    return "、".join(places) or "(結んだ本文なし)"


def candidate_items(session: Session) -> list[PendingReview]:
    items = []
    for idea in session.scalars(review_query.pending_select(Idea)).all():
        items.append(PendingReview(
            key=f"idea:{idea.id}",
            kind="候補",
            title=f"アイデア候補「{idea.name}」を確定・統合・削除する",
            detail="\n".join([
                idea.text or "(説明なし)",
                f"出てきた所: {_appearances(session, idea)}",
                gui_path(idea),
                f"種別: {idea.kind}",
                f"確定: GUI のレビュー画面で承認する / 退ける: 非承認にする / "
                f"統合: MergeIdea({idea.id}, 統合先の id) / 削除: DeleteIdea({idea.id})",
            ]),
        ))
    return items


def unconfirmed_meme_items(session: Session) -> list[PendingReview]:
    items = []
    for meme in session.scalars(review_query.pending_select(Meme)).all():
        items.append(PendingReview(
            key=f"meme:{meme.id}",
            kind="候補",
            title=f"ミーム候補「{meme.text}」を確かめる・直す・消す",
            detail="\n".join([
                meme.text,
                f"分類: {meme.category or '(未分類)'}",
                gui_path(meme),
                f"確定: GUI のレビュー画面で承認する(確定するまで人物へ引く対象に出ない) / 退ける: 非承認にする / "
                f"直す: UpdateMeme(MemeUpdateForm(id={meme.id}, ...)) / 削除: DeleteMeme({meme.id})",
            ]),
        ))
    return items


def unsynced_episode_items(session: Session) -> list[PendingReview]:
    items = []
    for episode in session.scalars(review_query.written_unsynced_episodes_select()).all():
        story = session.get(Story, episode.story_id)
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


def todo_items(session: Session) -> list[PendingReview]:
    items = []
    for model in review_query.text_models():
        for record in session.scalars(review_query.todo_select(model)).all():
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
