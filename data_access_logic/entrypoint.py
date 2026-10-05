#!/usr/bin/env python3
"""入口の基底。同じ入口を、呼ぶ側が使い分ける。

- claude が CLI から: `show()`(結果を JSON で print する)
- python から続けて使う: `run()`(`model_dump(mode="json")` した dict を返す)
- GUI の API: 自分のセッションで `execute(s)`(レスポンスのモデルを返す。確定のあとの AI の段は回さない)
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.interfaces import ORMOption

from data_access_logic.logs import configure_logging
from data_access_logic.material import Material
from db.schema import Base, Character, Location, get_env_session


class UnknownRecordError(ValueError):
    pass


class UnknownFieldError(ValueError):
    pass


def dumped(result: BaseModel | Sequence[BaseModel]) -> dict | list[dict]:
    """一覧を返す入口は、モデルのリストを返す。"""
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    return [item.model_dump(mode="json") for item in result]


def loading(query: Select, record_model: type[Material]) -> Select:
    """`record_model` に詰めるのに要る noload のリレーション(当事者・登場人物)を読む。
    同じセッションに行が残っていると eager load が効かないので `populate_existing` を付ける。"""
    return query.options(*record_model.LOAD_OPTIONS).execution_options(populate_existing=True)


def reloaded[R: Base](s: Session, row: R, *options: ORMOption) -> R:
    model = type(row)
    return s.scalars(select(model).where(model.id == row.id).options(*options)
                     .execution_options(populate_existing=True)).one()


def record_of[M: Material](s: Session, record_model: type[M], row: Base) -> M:
    if record_model.LOAD_OPTIONS:
        row = reloaded(s, row, *record_model.LOAD_OPTIONS)
    return record_model.model_validate(row)


class Entrypoint:
    def run(self) -> dict | list[dict]:
        return dumped(self.result())

    def show(self) -> None:
        configure_logging()
        print(json.dumps(self.run(), ensure_ascii=False, indent=2))

    def result(self) -> BaseModel | Sequence[BaseModel]:
        raise NotImplementedError


class SessionEntrypoint(Entrypoint):
    def result(self) -> BaseModel | Sequence[BaseModel]:
        with get_env_session() as s:
            return self.execute(s)

    def execute(self, s: Session) -> BaseModel | Sequence[BaseModel]:
        raise NotImplementedError


# `select()` の行を一つずつ `row()` でモデルにして並べる(docstring を持たせると、継いだ入口の説明として GUI に出てしまう)
class ListEntrypoint(SessionEntrypoint):
    def execute(self, s: Session) -> list[BaseModel]:
        return [self.row(row) for row in s.scalars(self.select()).all()]

    def select(self) -> Select:
        raise NotImplementedError

    def row(self, row: Any) -> BaseModel:
        raise NotImplementedError


# `execute()` は `s.begin()` に包むので、その中で `s.commit()` は呼ばない
# (成功時は抜けるときにまとめて commit、例外時は rollback される。docstring にすると、継いだ入口の説明として GUI に出てしまう)
class CommitEntrypoint(SessionEntrypoint):
    def result(self) -> BaseModel | Sequence[BaseModel]:
        with get_env_session() as s, s.begin():
            return self.execute(s)

    @staticmethod
    def check_exists(s: Session, model: type[Base], id_: int | None, label: str) -> None:
        if id_ is not None and s.get(model, id_) is None:
            raise UnknownRecordError(
                f"{label}={id_} という id の {model.__tablename__} が見つからない")

    @classmethod
    def check_knowers(cls, s: Session, form: BaseModel) -> None:
        """来歴・履歴の行の `knowers`(知る相手)の人物・場所があるか。"""
        for knower in (knower for row in (getattr(form, "histories", None) or []) for knower in (row.knowers or [])):
            cls.check_exists(s, Character, knower.knower_id, "knowers.knower_id")
            cls.check_exists(s, Location, knower.location_id, "knowers.location_id")

    @staticmethod
    def finalize(s: Session, record: Base) -> None:
        """`StampType` のような列は bind するとき(`process_bind_param`)にしか
        型変換が掛からない。`flush` しただけでは record の属性は渡した生の値のまま残るので、
        レスポンスのモデルに詰める前に `refresh` で db に書いた値を読み直し、
        `process_result_value` を通した本来の型(`Stamp` 等)に揃える。
        """
        s.flush()
        s.refresh(record)


class RandomDraft(Entrypoint):
    """db に触れない下書き。返した形のまま、確定する入口の引数に渡せる。"""

    # `randomizer/` の factory。確定する入口の引数のモデルをそのまま組む
    builder: staticmethod

    def __init__(self, **overrides: Any) -> None:
        self.overrides = overrides

    def result(self) -> BaseModel:
        return self.builder(**self.overrides)
