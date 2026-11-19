#!/usr/bin/env python3
"""行を一つずつ書く入口へのリクエストを並べて送り、一つのトランザクションで順に書く。一つでも通らなければ何も書かない。

    RunBatch(requests=[
        BatchRequest(entrance="character.update_history.UpdateCharacterHistory",
                     args={"history_id": 40, "history": {"description": "港で疫病に罹る"}}),
        BatchRequest(entrance="idea.delete_history.DeleteIdeaHistory", args={"history_id": 30}),
    ]).show()
"""
from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.batch.form import BatchRequest
from data_access_logic.entrance_args import built
from data_access_logic.entrypoint import CommitEntrypoint, UnknownRecordError
from data_access_logic.story.scope import HISTORY_MODELS, args_scope_in
from db import story_scope
from db.guard import ProtectedRowError

# 呼べる入口。行を一つずつ足す・直す・消す入口だけにする。どれも db の書き込み(`execute`)だけを回し、話・出来事の確定のあとの
# AI の段(ミーム・要約)は回さない(GUI の表の修正と同じ)
BATCH_ENTRANCES = frozenset({
    "character.add_knower.AddKnower",
    "character.append_history.AppendCharacterHistory",
    "character.append_relation_history.AppendRelationHistory",
    "character.append_skill_history.AppendSkillHistory",
    "character.delete_history.DeleteCharacterHistory",
    "character.delete_relation_history.DeleteRelationHistory",
    "character.delete_skill_history.DeleteSkillHistory",
    "character.update_history.UpdateCharacterHistory",
    "character.update_relation_history.UpdateRelationHistory",
    "character.update_skill_history.UpdateSkillHistory",
    "episode.commit_episode.CommitEpisode",
    "event.update_event.UpdateEvent",
    "idea.append_history.AppendIdeaHistory",
    "idea.delete_history.DeleteIdeaHistory",
    "idea.update_history.UpdateIdeaHistory",
    "location.append_history.AppendLocationHistory",
    "location.delete_history.DeleteLocationHistory",
    "location.update_history.UpdateLocationHistory",
    "story.update_story.UpdateStory",
})


@contextmanager
def _labelled(index: int, request: BatchRequest) -> Iterator[None]:
    """どのリクエストで止まったかを、止まった理由の頭に付ける。守り・行の無いことは同じ型のまま上げる(API の 403・404)。"""
    label = f"requests[{index}] {request.entrance}"
    try:
        yield
    except (ProtectedRowError, UnknownRecordError) as error:
        raise type(error)(f"{label}: {error}") from error
    except ValueError as error:
        raise ValueError(f"{label}: {error}") from error


def _entrance(request: BatchRequest) -> CommitEntrypoint:
    if request.entrance not in BATCH_ENTRANCES:
        raise ValueError("バッチで呼べない入口")
    module_name, _, class_name = request.entrance.rpartition(".")
    return built(getattr(importlib.import_module(f"data_access_logic.{module_name}"), class_name), request.args)


class RunBatch(CommitEntrypoint):
    """結果は、リクエストの順に、それぞれの入口が一件だけ呼ばれたときと同じもの。書いたあとの確かめ(親の付け替えの循環など)は、
    全部のリクエストを書いてからする。"""

    # リクエストごとに引数から作品を決める(決まらなければ、呼んだ画面の作品)
    STORY_FROM_ARGS = False

    def __init__(self, requests: list[BatchRequest]):
        self.requests = requests
        self.scopes: list[story_scope.Scope] = []

    def run(self) -> list[dict]:
        """結果も、リクエストごとに引数を読んだ作品の暦で書き出す(書き出すときの文脈の暦で表記が決まるので)。"""
        results = self.result()
        assert isinstance(results, list)
        dumped = []
        for result, scope in zip(results, self.scopes):
            with story_scope.scoped(scope):
                dumped.append(result.model_dump(mode="json"))
        return dumped

    def execute(self, s: Session) -> list[BaseModel]:
        # 引数の時刻は、リクエストごとに引数から決めた作品の暦で読む
        self.scopes = scopes = [
            args_scope_in(s, request.args, history_model=HISTORY_MODELS.get(request.entrance.rpartition(".")[0]))
            for request in self.requests]
        entrances = []
        for index, (request, scope) in enumerate(zip(self.requests, scopes)):
            with _labelled(index, request), story_scope.scoped(scope):
                entrances.append(_entrance(request))
        results = []
        for index, (request, entrance, scope) in enumerate(zip(self.requests, entrances, scopes)):
            with _labelled(index, request), story_scope.scoped(scope):
                results.append(entrance.execute(s))
                # 書き手の守りは書き出すときに止めるので、どのリクエストで止まったかが分かるよう一件ずつ書き出す
                s.flush()
        for index, (request, entrance) in enumerate(zip(self.requests, entrances)):
            with _labelled(index, request):
                entrance.verify(s)
        return results
