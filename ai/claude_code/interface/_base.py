#!/usr/bin/env python3
from __future__ import annotations

import json

from db.schema import get_env_session
from db.schema_pydantic import to_dict


class Entrypoint:
    def run(self):
        raise NotImplementedError


class SessionEntrypoint(Entrypoint):
    def run(self):
        with get_env_session() as session:
            return self.execute(session)

    def execute(self, session):
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

    def run(self):
        with get_env_session() as session:
            with session.begin():
                return self.execute(session)

    @staticmethod
    def parse(payload: str | dict) -> dict:
        return json.loads(payload) if isinstance(payload, str) else dict(payload)

    @staticmethod
    def check_exists(session, model, id_: int | None, label: str) -> None:
        if id_ is not None and session.get(model, id_) is None:
            raise UnknownRecordError(
                f"{label}={id_} という id の {model.__tablename__} が見つからない")

    @staticmethod
    def finalize(session, record):
        """`StampType` のような列は bind するとき(`process_bind_param`)にしか
        型変換が掛からない。`flush` しただけでは record の属性は渡した生の値
        (例: 文字列の `"1"`)のまま残るので、`to_dict` に渡す前に `refresh` で
        db に書いた値を読み直し、`process_result_value` を通した本来の型
        (`Stamp` 等)に揃える。
        """
        session.flush()
        session.refresh(record)

    def check_columns(self, data: dict, model: type | None = None) -> None:
        model = model or self.model
        columns = {column.key for column in model.__table__.columns} - {"id"}
        unknown = set(data) - columns
        if unknown:
            raise UnknownFieldError(
                f"{model.__name__} のスキーマに無い欄: {sorted(unknown)}")

    @staticmethod
    def require_id(data: dict, label: str) -> int:
        """更新・確定の対象を指す `id` を data から取り出す。無ければ入力ミス。"""
        id_ = data.pop("id", None)
        if id_ is None:
            raise ValueError(f"id は必須({label})")
        return id_

    def get_or_raise(self, session, id_, label: str, model: type | None = None):
        """自分自身の id で行を引く。見つからなければ 404 相当の `UnknownRecordError`。"""
        model = model or self.model
        record = session.get(model, id_)
        if record is None:
            raise UnknownRecordError(f"id={id_} という{label}が見つからない")
        return record

    def apply(self, session, record, data: dict) -> dict:
        """残った列を setattr してから `finalize` し、`to_dict` で返す。"""
        for key, value in data.items():
            setattr(record, key, value)
        self.finalize(session, record)
        return to_dict(record)
