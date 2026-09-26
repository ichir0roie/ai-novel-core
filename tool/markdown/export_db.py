#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from decimal import Decimal

from sqlalchemy import inspect as sa_inspect

from db.child_lists import dump_children
from db.schema import WORLDS_ROOT, Base, MarkdownBase, get_novel_session
from db.stamp import Stamp
from tool.map.render import render_maps
from tool.markdown.sync_manifest import Manifest, digest, locked, read_text
from tool.relation.render import render_relations


__all__ = ["WORLDS_ROOT", "ExportError", "export_db", "export_changes", "render_row", "edited_markdown",
           "parent_of", "markdown_path"]

IGNORE_COLUMNS = {"directory_path", "filename"}

_SHOW_LIMIT = 5


class ExportError(ValueError):
    pass


def parent_of(model: type) -> tuple[type, str] | None:
    """`MARKDOWN_PARENT` の指す親のモデルと、親を指す列の名前。親の md の下に置かないモデルは None"""
    if model.MARKDOWN_PARENT is None:
        return None
    relation = sa_inspect(model).relationships[model.MARKDOWN_PARENT]
    return relation.mapper.class_, next(iter(relation.local_columns)).key


def _depth(model: type) -> int:
    parent = parent_of(model)
    return 0 if parent is None else 1 + _depth(parent[0])


def _markdown_models() -> list[type]:
    """親の md の下に置くモデルは、親より後に並べる(親の置き場所から自分の置き場所を決めるため)。"""
    models = [
        mapper.class_ for mapper in Base.registry.mappers
        if issubclass(mapper.class_, MarkdownBase) and mapper.class_ is not MarkdownBase
    ]
    return sorted(models, key=_depth)


def _top_models(models: list[type]) -> list[type]:
    return [model for model in models if parent_of(model) is None]


def _serialize(value):
    if isinstance(value, Stamp):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def _render(data: dict, sections: dict[str, str]) -> str:
    data_json = json.dumps(data, ensure_ascii=False, indent=2)
    body = "".join(f"\n# {name}\n{value}\n" for name, value in sections.items())
    return f"# data\n```json\n{data_json}\n```\n{body}"


def _row_data(model: type, row, ignore_columns: set[str]) -> dict:
    ignored = ignore_columns | set(model.TEXT_SECTIONS)
    data = {
        column.key: _serialize(getattr(row, column.key))
        for column in model.__table__.columns
        if column.key not in ignored
    }
    for name in model.CHILD_LISTS:
        data[name] = [{key: _serialize(value) for key, value in item.items()}
                      for item in dump_children(row, name)]
    return data


def _sections(model: type, row) -> dict[str, str]:
    return {name: getattr(row, name) or "" for name in model.TEXT_SECTIONS}


def render_row(model: type, row) -> str:
    if model.MARKDOWN_BODY_ONLY:
        return f"{row.text or ''}\n"
    return _render(_row_data(model, row, IGNORE_COLUMNS), _sections(model, row))


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _markdown_files(root: str, models: list[type]) -> list[str]:
    """親の md の下に置くモデルの md も、親のテーブルのディレクトリをたどって拾う。"""
    paths = []
    for model in _top_models(models):
        for dirpath, _dirnames, filenames in os.walk(os.path.join(root, model.__tablename__)):
            paths.extend(os.path.normpath(os.path.join(dirpath, name))
                         for name in filenames if name.endswith(".md"))
    return sorted(paths)


def _remove_empty_dirs(top: str) -> None:
    for dirpath, _dirnames, _filenames in os.walk(top, topdown=False):
        if dirpath != top and not os.listdir(dirpath):
            os.rmdir(dirpath)


def _directory(root: str, model: type, row, placed: dict[tuple[type, int], str]) -> str:
    parent = parent_of(model)
    if parent is None:
        table_dir = os.path.join(root, model.__tablename__)
        return os.path.join(table_dir, row.directory_path) if row.directory_path else table_dir
    parent_model, column = parent
    parent_path = placed.get((parent_model, getattr(row, column)))
    if parent_path is None:
        raise ExportError(
            f"{model.__tablename__} id={row.id} の親 {parent_model.__tablename__} "
            f"id={getattr(row, column)} が無いので、md の置き場所が決まらない")
    return parent_path[: -len(".md")]


def markdown_path(session, row) -> str:
    """行の md の、`worlds/` からの相対パス(/ 区切り)。同名の md が他にあるときの逃がし先は考えない。"""
    model = type(row)
    parent = parent_of(model)
    if parent is None:
        parts = [model.__tablename__, row.directory_path]
    else:
        parent_row = session.get(parent[0], getattr(row, parent[1]))
        parts = [markdown_path(session, parent_row)[: -len(".md")]]
    return "/".join(part for part in [*parts, row.markdown_name] if part)


def _expected(session, root: str, models: list[type]) -> tuple[dict[str, tuple], dict[str, int]]:
    """書き出すはずの md のパスごとに、(モデル, 行, 中身)。`models` は `_markdown_models()` の並びで渡す。"""
    expected: dict[str, tuple] = {}
    counts: dict[str, int] = {}
    placed: dict[tuple[type, int], str] = {}
    for model in models:
        rows = session.query(model).order_by(model.id.asc()).all()
        for row in rows:
            dir_path = _directory(root, model, row, placed)
            # `directory_path` は / 区切りなので、walk で拾ったパスと比べられるよう揃える
            path = os.path.normpath(os.path.join(dir_path, row.markdown_name))
            if path in expected:
                # 名前に id を含まないテーブルで同名になったら、id を頭に付けた(import が読める)名前へ逃がす
                path = os.path.normpath(os.path.join(dir_path, f"{row.id}_{row.markdown_name}"))
            expected[path] = (model, row, render_row(model, row))
            placed[(model, row.id)] = path
        counts[model.__tablename__] = len(rows)
    return expected, counts


def edited_markdown(root: str, manifest: Manifest | None = None) -> list[str]:
    """前回の同期より後に手で直された(または手で足された・消された)md。台帳が無ければ比べようがないので空。"""
    manifest = manifest or Manifest(root)
    if not manifest.exists:
        return []
    edited = [path for path in _markdown_files(root, _markdown_models())
              if manifest.edited(path, read_text(path))]
    return sorted(edited + manifest.missing())


def check_no_hand_edits(root: str, manifest: Manifest | None = None) -> None:
    edited = edited_markdown(root, manifest)
    if not edited:
        return
    shown = "\n".join(edited[:_SHOW_LIMIT])
    rest = len(edited) - _SHOW_LIMIT
    if rest > 0:
        shown += f"\n(ほか {rest} 件)"
    raise ExportError(
        "前回の同期より後に手で直された・消された md がある。書き出すと手で入れた変更が失われる:\n"
        f"{shown}\n"
        "SyncDb() で取り込んでから書き出す。md を捨ててよいなら ExportDb(force=True)。")


def export_changes(session, root: str, manifest: Manifest) -> dict:
    """db と中身の違う md だけを書き直し、db に行の無い md を消す。

    手で直された md が残っていても上書きするので、呼ぶ前に取り込むか確かめておく。
    """
    models = _markdown_models()
    expected, counts = _expected(session, root, models)
    written = []
    for path, (model, row, text) in expected.items():
        if not os.path.exists(path) or read_text(path) != text:
            _write(path, text)
            written.append(path)
        manifest.set(path, model.__tablename__, row.id, digest(text), digest(text))

    removed = []
    for path in _markdown_files(root, models):
        if path not in expected:
            os.remove(path)
            removed.append(path)
    kept = {manifest.key(path) for path in expected}
    manifest.entries = {key: entry for key, entry in manifest.entries.items() if key in kept}
    for model in _top_models(models):
        _remove_empty_dirs(os.path.join(root, model.__tablename__))

    maps = {os.path.normpath(path) for path in render_maps(session, root)}
    location_dir = os.path.join(root, "location")
    for dirpath, _dirnames, filenames in os.walk(location_dir):
        for name in filenames:
            path = os.path.normpath(os.path.join(dirpath, name))
            if name.endswith("_map.svg") and path not in maps:
                os.remove(path)
    render_relations(session, root)
    return {"counts": counts, "written": written, "removed": removed}


def export_db(root: str = WORLDS_ROOT, force: bool = False) -> dict[str, int]:
    with locked(root):
        manifest = Manifest(root)
        if not force:
            check_no_hand_edits(root, manifest)
        with get_novel_session() as session:
            result = export_changes(session, root, manifest)
        manifest.save()
    return result["counts"]


if __name__ == "__main__":
    export_db()
