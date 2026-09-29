#!/usr/bin/env python3
"""確定したあとに AI(`claude -p`)を回す入口の基底。

AI の段は `run()` / `show()` のときだけ回る。GUI の API が呼ぶ `execute(session)` は確定だけを行い、
取りこぼした分は `RefreshGeneratedContent` が後でまとめて拾う。
"""
from __future__ import annotations

from pydantic import BaseModel

from ai.claude_code import ai_client, fact_checker
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.episode import summary as episode_summary
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.event import summary as event_summary
from data_access_logic.event.record import EventRecord
from data_access_logic.idea.record import IdeaRecord
from data_access_logic.meme.extractor import refresh
from data_access_logic.oracle.record import OracleRecord
from data_access_logic.story.record import StoryRecord
from db.schema import Episode, Event, get_env_session


class CommitAndRefresh(CommitEntrypoint):
    """記録を確定したあと、確定のトランザクションを閉じてからミーム抽出と、出来事・話ならその要約を
    追いかける基底(AI が答えなくても確定自体は残るよう、別のセッションで行う)。
    """

    def execute(self, session) -> EventRecord | EpisodeRecord | StoryRecord:
        raise NotImplementedError

    def result(self) -> EventRecord | EpisodeRecord | StoryRecord:
        with get_env_session() as session, session.begin():
            committed = self.execute(session)
        with get_env_session() as session:
            refresh(session, ai_client)
            row = session.get_one(self.model, committed.id)
            if isinstance(row, Event):
                event_summary.summarize(session, ai_client, row)
            elif isinstance(row, Episode):
                episode_summary.summarize(session, ai_client, row)
            self.follow_up(session)
        return committed

    def follow_up(self, session) -> None:
        """入口ごとに足す、確定したあとの AI の段。"""


class MemeSourceCommitted(BaseModel):
    """確定した行と、そのあと足したミームの件数。"""

    record: IdeaRecord | OracleRecord
    memes_added: int


class CommitMemeSource(CommitEntrypoint):
    """ミームの元(アイデア・oracle)を確定したあと、その場でミームを抜き出す基底。

    抜き出しは確定のトランザクションを閉じてから行う(AI が答えなくても確定は残し、
    `meme_seeded` が false のまま次の抽出に回す)。
    `fact_check` が立っていれば、抜き出す前に確定したもの自身を AI に検めさせ、検証結果を
    足した本文からミームを抜き出す。足したミームも検めさせる。
    """

    fact_check = True

    def execute(self, session) -> IdeaRecord | OracleRecord:
        raise NotImplementedError

    def result(self) -> MemeSourceCommitted:
        with get_env_session() as session, session.begin():
            committed = self.execute(session)
        with get_env_session() as session:
            if self.fact_check and committed.text.strip():
                fact_checker.check(session, self.model.__tablename__, ids=[committed.id])
            last_id = fact_checker.last_meme_id(session)
            memes_added = refresh(session, ai_client)
            if self.fact_check:
                fact_checker.check_new_memes(session, last_id)
            # 検めた結果は本文の末尾に足されるので、読み直して返す
            record = type(committed).model_validate(session.get_one(self.model, committed.id))
        return MemeSourceCommitted(record=record, memes_added=memes_added)
