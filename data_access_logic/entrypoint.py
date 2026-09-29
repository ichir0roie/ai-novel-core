#!/usr/bin/env python3
"""入口の基底。同じ入口を、呼ぶ側が使い分ける。

- claude が CLI から: `show()`(結果を JSON で print する)
- python から続けて使う: `run()`(`model_dump(mode="json")` した dict を返す)
- GUI の API: 自分のセッションで `execute(session)`(レスポンスのモデルを返す。確定のあとの AI の段は回さない)
"""
from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel
from sqlalchemy import select

from data_access_logic.material import Material
from db.schema import get_env_session


class UnknownRecordError(ValueError):
    pass


class UnknownFieldError(ValueError):
    pass


def dumped(result: BaseModel | Sequence[BaseModel]) -> dict | list[dict]:
    """一覧を返す入口は、モデルのリストを返す。"""
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    return [item.model_dump(mode="json") for item in result]


def loading(query, record_model: type[Material]):
    """`record_model` に詰めるのに要る noload のリレーション(当事者・登場人物)を読む。
    同じセッションに行が残っていると eager load が効かないので `populate_existing` を付ける。"""
    return query.options(*record_model.LOAD_OPTIONS).execution_options(populate_existing=True)


def reloaded(session, row, *options):
    model = type(row)
    return session.scalars(select(model).where(model.id == row.id).options(*options)
                           .execution_options(populate_existing=True)).one()


def record_of[M: Material](session, record_model: type[M], row) -> M:
    if record_model.LOAD_OPTIONS:
        row = reloaded(session, row, *record_model.LOAD_OPTIONS)
    return record_model.model_validate(row)


class Entrypoint:
    def run(self) -> dict | list[dict]:
        return dumped(self.result())

    def show(self) -> None:
        print(json.dumps(self.run(), ensure_ascii=False, indent=2))

    def result(self) -> BaseModel | Sequence[BaseModel]:
        raise NotImplementedError


class SessionEntrypoint(Entrypoint):
    def result(self) -> BaseModel | Sequence[BaseModel]:
        with get_env_session() as session:
            return self.execute(session)

    def execute(self, session) -> BaseModel | Sequence[BaseModel]:
        raise NotImplementedError


# `select()` の行を一つずつ `row()` でモデルにして並べる(docstring を持たせると、継いだ入口の説明として GUI に出てしまう)
class ListEntrypoint(SessionEntrypoint):
    def execute(self, session) -> list[BaseModel]:
        return [self.row(row) for row in session.scalars(self.select()).all()]

    def select(self):
        raise NotImplementedError

    def row(self, row) -> BaseModel:
        raise NotImplementedError


class CommitEntrypoint(SessionEntrypoint):
    """`execute()` は `session.begin()` に包むので、その中で `session.commit()` は呼ばない
    (成功時は抜けるときにまとめて commit、例外時は rollback される)。
    """

    model: type

    def result(self) -> BaseModel | Sequence[BaseModel]:
        with get_env_session() as session, session.begin():
            return self.execute(session)

    @staticmethod
    def check_exists(session, model, id_: int | None, label: str) -> None:
        if id_ is not None and session.get(model, id_) is None:
            raise UnknownRecordError(
                f"{label}={id_} という id の {model.__tablename__} が見つからない")

    @staticmethod
    def finalize(session, record):
        """`StampType` のような列は bind するとき(`process_bind_param`)にしか
        型変換が掛からない。`flush` しただけでは record の属性は渡した生の値のまま残るので、
        レスポンスのモデルに詰める前に `refresh` で db に書いた値を読み直し、
        `process_result_value` を通した本来の型(`Stamp` 等)に揃える。
        """
        session.flush()
        session.refresh(record)


class RandomDraft(Entrypoint):
    """db に触れない下書き。返した形のまま、確定する入口の引数のモデルに読み込める。"""

    builder: staticmethod
    draft_model: type[BaseModel]

    def __init__(self, **overrides):
        self.overrides = overrides

    def result(self) -> BaseModel:
        return self.draft_model.model_validate(self.builder(**self.overrides))
