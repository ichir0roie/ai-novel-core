#!/usr/bin/env python3
"""入口の引数のモデルの欄から、フォームを組み立てるための情報を作る。"""
from __future__ import annotations

import enum
import typing
from typing import Any

from pydantic.fields import FieldInfo

from data_access_logic.material import References
from gui.api.models import ColumnMeta


def _members(annotation: Any) -> tuple:
    """`X | None` や `list[X]` を開いた中身。"""
    return (annotation, *typing.get_args(annotation))


def choices_of(field: FieldInfo) -> list[str] | None:
    for member in _members(field.annotation):
        if isinstance(member, type) and issubclass(member, enum.Enum):
            return [choice.value for choice in member]
    return None


def references_of(field: FieldInfo) -> str | None:
    for mark in field.metadata:
        if isinstance(mark, References):
            return mark.table
    return None


def field_meta(key: str, field: FieldInfo, create_only: bool = False) -> ColumnMeta:
    """表の列でない欄(出来事の当事者など)。説明・指す先は欄の `description` / `References` に書く。"""
    is_list = any(typing.get_origin(member) is list for member in _members(field.annotation))
    return ColumnMeta(
        key=key, type="id_list" if is_list else "integer",
        nullable=not field.is_required(), required=field.is_required(), references=references_of(field),
        create_only=create_only, comment=field.description)
