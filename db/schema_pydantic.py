#!/usr/bin/env python3
from __future__ import annotations

import enum
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, create_model
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase

import db.schema as schema
from db.child_lists import dump_children
from db.stamp import Stamp

# 列の型 → pydantic (python) の型
_TYPE_MAP = {
    Decimal: float,
}


def _python_type(column_type) -> type:
    py_type = column_type.python_type
    return _TYPE_MAP.get(py_type, py_type)


def _field_type(column) -> type:
    if isinstance(column.type, schema.StampType):
        py_type = Stamp
    elif isinstance(column.type, schema.ConfirmStatusType):
        py_type = schema.ConfirmStatus
    elif isinstance(column.type, schema.PolygonType):
        py_type = dict
    else:
        py_type = _python_type(column.type)
    return py_type | None if column.nullable else py_type


_MODELS: dict[type, type[BaseModel]] = {}


def _build_model(orm_cls: type[DeclarativeBase]) -> type[BaseModel]:
    mapper = sa_inspect(orm_cls)
    fields: dict[str, Any] = {}
    for column in mapper.columns:
        default = None if column.nullable or column.primary_key else ...
        fields[column.key] = (_field_type(column), default)

    model = create_model(
        orm_cls.__name__,
        __config__=ConfigDict(from_attributes=True, arbitrary_types_allowed=True),
        **fields,
    )
    return model


def _model_for(orm_cls: type[DeclarativeBase]) -> type[BaseModel]:
    model = _MODELS.get(orm_cls)
    if model is None:
        model = _build_model(orm_cls)
        _MODELS[orm_cls] = model
    return model


def to_model(row) -> BaseModel:
    return _model_for(type(row)).model_validate(row)


def to_dict(row) -> dict:
    data = to_model(row).model_dump()
    for name in getattr(type(row), "CHILD_LISTS", ()):
        data[name] = dump_children(row, name)
    for name in getattr(type(row), "COMPUTED_COLUMNS", ()):
        data[name] = getattr(row, name)
    return _to_jsonable(data)


def _to_jsonable(value):
    if isinstance(value, Stamp):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _to_jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(val) for val in value]
    return value
