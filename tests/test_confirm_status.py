"""`confirmed` の三段(未確認/承認/非承認)。以前の bool からの読み替えと、非承認が候補・検索・引き出しに出ないこと。"""
import random

import pytest
from sqlalchemy.exc import StatementError

from ai.time_keeper import idea_context
from ai.time_keeper import meme as meme_module
from data_access_logic.query import common_query, dictionary_query, meme_query, review_query
from db.schema import ConfirmStatus, Idea, Location, Meme, parse_confirm_status


def test_parse_accepts_legacy_bool_and_rejects_unknown():
    assert parse_confirm_status(True) == "承認" and parse_confirm_status(False) == "未確認"
    assert parse_confirm_status("true") == "承認" and parse_confirm_status("false") == "未確認"
    assert parse_confirm_status("1") == "承認" and parse_confirm_status(0) == "未確認"
    assert parse_confirm_status(ConfirmStatus.REJECTED) == "非承認"
    assert parse_confirm_status(" 承認 ") == "承認"
    assert parse_confirm_status(None) is None and parse_confirm_status("") is None
    with pytest.raises(ValueError, match="confirmed は"):
        parse_confirm_status("maybe")


def test_defaults_and_legacy_values_are_stored_as_statuses(session):
    idea = Idea(name="魔力", kind="技術", text="")
    legacy = Idea(name="宿り", kind="技術", text="", confirmed=False)
    meme = Meme(text="約束を守る", category="信条")
    session.add_all([idea, legacy, meme])
    session.commit()
    session.expire_all()

    assert idea.confirmed == ConfirmStatus.APPROVED
    assert legacy.confirmed == ConfirmStatus.PENDING
    assert meme.confirmed == ConfirmStatus.PENDING

    # bind 時の ValueError は SQLAlchemy が StatementError に包む
    with pytest.raises(StatementError, match="confirmed は"):
        session.add(Idea(name="変", kind="技術", text="", confirmed="maybe"))
        session.commit()
    session.rollback()


def test_rejected_rows_are_left_out_everywhere(session):
    world = Location(name="世界線", kind="世界線", text="")
    session.add(world)
    session.flush()
    approved = Idea(name="魔力", kind="技術", text="", location_id=world.id)
    pending = Idea(name="宿り", kind="技術", text="", location_id=world.id, confirmed=ConfirmStatus.PENDING)
    rejected = Idea(name="虫憑き", kind="呼称", text="", location_id=world.id, confirmed=ConfirmStatus.REJECTED)
    session.add_all([approved, pending, rejected])
    session.add_all([Meme(text="確かめた", category="信条", confirmed=ConfirmStatus.APPROVED),
                     Meme(text="未確認", category="信条"),
                     Meme(text="退けた", category="信条", confirmed=ConfirmStatus.REJECTED)])
    session.commit()

    assert [i.id for i in session.scalars(review_query.pending_select(Idea))] == [pending.id]
    assert [i.id for i in session.scalars(common_query.ideas_select([world.id]))] == [approved.id]
    assert [i.id for i in session.scalars(
        dictionary_query.ideas_by_terms_select(["虫憑き", "宿り", "魔力"]))] == [approved.id]
    assert {i.id for i in session.scalars(
        dictionary_query.ideas_by_terms_select(["虫憑き", "宿り", "魔力"], confirmed_only=False))} == {
            approved.id, pending.id, rejected.id}
    assert [m.text for m in session.scalars(review_query.pending_select(Meme))] == ["未確認"]
    drawn = meme_module.draw(session, random.Random(0), ("信条",) * 20)
    assert {d["text"] for d in drawn} <= {"確かめた"}


def test_rejected_term_is_not_re_added_as_a_candidate(session):
    session.add_all([Idea(name="虫憑き", kind="呼称", text="", confirmed=ConfirmStatus.REJECTED),
                     Idea(name="宿り", kind="技術", text="", confirmed=ConfirmStatus.PENDING)])
    session.commit()
    term = {"keyword": "虫憑き", "kind": "呼称", "description": "", "start": None, "end": None}

    assert idea_context._candidate_for(session, term, None) is None
    assert session.query(Idea).filter_by(name="虫憑き").count() == 1

    pending = idea_context._candidate_for(session, {**term, "keyword": "宿り", "kind": "技術"}, None)
    assert pending is not None and pending.confirmed == ConfirmStatus.PENDING
    assert session.query(Idea).filter_by(name="宿り").count() == 1
