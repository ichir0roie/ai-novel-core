#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client, fact_checker
from ai.claude_code.interface._base import CommitEntrypoint, Entrypoint
from ai.time_keeper import generated_content
from data_access_logic.meme.extractor import refresh
from db.schema import get_env_session


class RandomDraft(Entrypoint):
    builder: staticmethod

    def __init__(self, **overrides):
        self.overrides = overrides

    def run(self) -> dict:
        return self.builder(**self.overrides)


class CommitDraft(CommitEntrypoint):
    pass


class CommitAndRefresh(CommitDraft):
    """記録を確定したあと、確定のトランザクションを閉じてから `generated_content.refresh`
    でミーム抽出・要約を追いかける基底(AI が答えなくても確定自体は残るよう、別のセッションで行う)。
    """

    def run(self) -> dict:
        result = super().run()
        with get_env_session() as session:
            generated_content.refresh(session, ai_client, session.get(self.model, result["id"]))
        return result


class CommitMemeSource(CommitDraft):
    """ミームの元(アイデア・oracle)を確定したあと、その場でミームを抜き出す基底。

    抜き出しは確定のトランザクションを閉じてから行う(AI が答えなくても確定は残し、
    `meme_seeded` が false のまま次の抽出に回す)。足したミームの件数を `memes_added` で返す。
    `fact_check` が立っていれば、抜き出す前に確定したもの自身を AI に検めさせ、検証結果を
    足した本文からミームを抜き出す。足したミームも検めさせる。
    """

    fact_check = True

    def run(self) -> dict:
        result = super().run()
        with get_env_session() as session:
            if self.fact_check and result["text"].strip():
                fact_checker.check(session, self.model.__tablename__, ids=[result["id"]])
                result["text"] = session.get(self.model, result["id"]).text
            last_id = fact_checker.last_meme_id(session)
            result["memes_added"] = refresh(session, ai_client)
            if self.fact_check:
                fact_checker.check_new_memes(session, last_id)
        return result
