#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from ai.time_keeper import idea_context
from data_access_logic.query import dictionary_query, review_query
from db.schema import Idea, Story
from tool.markdown import export_db


def md_path(session: Session, record) -> str:
    return f"worlds/{export_db.markdown_path(session, record)}"


def _label(record) -> str:
    for column in ("name", "title"):
        value = getattr(record, column, None)
        if value:
            return value
    return f"id={record.id}"


def _appearances(session: Session, idea: Idea) -> str:
    places = []
    for table, records in idea_context.linked_records(session, idea.id).items():
        places += [f"{table}「{_label(record)}」(id={record.id})" for record in records]
    return "、".join(places) or "(結んだ本文なし)"


def candidate_items(session: Session) -> list[dict]:
    items = []
    for idea in session.scalars(dictionary_query.auto_generated_ideas_select()).all():
        items.append({
            "key": f"idea:{idea.id}",
            "kind": "候補",
            "title": f"アイデア候補「{idea.name}」を確定・統合・削除する",
            "detail": "\n".join([
                idea.text or "(説明なし)",
                f"出てきた所: {_appearances(session, idea)}",
                f"md: {md_path(session, idea)}",
                f"種別: {idea.kind}",
                f"確定: md の auto_generated を false にする / "
                f"統合: MergeIdea({idea.id}, 統合先の id) / 削除: DeleteIdea({idea.id})",
            ]),
        })
    return items


def unsynced_plot_items(session: Session) -> list[dict]:
    items = []
    for plot in session.scalars(review_query.written_unsynced_plots_select()).all():
        story = session.get(Story, plot.story_id)
        story_name = story.name if story else f"作品 id={plot.story_id}"
        items.append({
            "key": f"plot:{plot.id}",
            "kind": "未同期の話",
            "title": f"{story_name}「{plot.title}」を世界観へ反映して synced を立てる",
            "detail": "\n".join([
                "本文の出来事・行動を台帳へ戻す。戻すまで、この作品の次の話が書けない。",
                f"md: {md_path(session, plot)}",
                f"済んだら: SetPlotSynced({plot.id})",
            ]),
        })
    return items


def todo_items(session: Session) -> list[dict]:
    items = []
    for model in review_query.markdown_models():
        for record in session.scalars(review_query.todo_select(model)).all():
            lines = [line.strip() for name in model.TEXT_SECTIONS
                     for line in (getattr(record, name) or "").splitlines()
                     if review_query.TODO_MARK in line]
            items.append({
                "key": f"todo:{model.__tablename__}:{record.id}",
                "kind": "TODO",
                "title": f"TODO を片付ける: {model.__tablename__}「{_label(record)}」",
                "detail": "\n".join([*lines, f"md: {md_path(session, record)}"]),
            })
    return items
