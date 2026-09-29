#!/usr/bin/env python3
from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel
from sqlalchemy import select

from db.schema import get_env_session


def dumped(result: BaseModel | Sequence[BaseModel]) -> dict | list[dict]:
    """一覧を返す入口は、モデルのリストを返す。"""
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    return [item.model_dump(mode="json") for item in result]


def reloaded(session, record, *options):
    """noload のリレーションを読み直す。同じセッションに行が残っていると eager load が効かないので `populate_existing` を付ける。"""
    model = type(record)
    return session.scalars(select(model).where(model.id == record.id).options(*options)
                           .execution_options(populate_existing=True)).one()


class Entrypoint:
    def run(self) -> dict | list[dict]:
        return dumped(self.result())

    def show(self) -> None:
        """claude が CLI から呼ぶとき用。結果を続けて python で使うなら `run()` を呼ぶ。"""
        print(json.dumps(self.run(), ensure_ascii=False, indent=2))

    def result(self) -> BaseModel | Sequence[BaseModel]:
        raise NotImplementedError


class SessionEntrypoint(Entrypoint):
    def result(self) -> BaseModel | Sequence[BaseModel]:
        with get_env_session() as session:
            return self.execute(session)

    def execute(self, session) -> BaseModel | Sequence[BaseModel]:
        raise NotImplementedError


class UnknownRecordError(ValueError):
    pass


class UnknownFieldError(ValueError):
    pass


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

    def get_or_raise(self, session, id_, label: str, model: type | None = None):
        """自分自身の id で行を引く。見つからなければ 404 相当の `UnknownRecordError`。"""
        model = model or self.model
        record = session.get(model, id_)
        if record is None:
            raise UnknownRecordError(f"id={id_} という{label}が見つからない")
        return record

    def apply(self, session, record, values: dict) -> None:
        for key, value in values.items():
            setattr(record, key, value)
        self.finalize(session, record)
