#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
import json
import os
import re
import shutil

from sqlalchemy import String, delete, select

from ai.claude_code import ai_client
from ai.time_keeper import idea_kind
from db.child_lists import ChildListError, load_children
from db.schema import (
    NOVEL_DB_PATH, RECORD_PREFIX, WORLDS_ROOT, Base, ConfirmStatusType, Idea, MarkdownBase, StampType,
    get_novel_session, parse_confirm_status,
)
from db.stamp import Stamp
from tool.markdown import export_db
from tool.markdown.sync_manifest import Manifest, digest, locked, read_text


__all__ = ["WORLDS_ROOT", "ImportDbError", "import_db", "import_changes"]


class ImportDbError(ValueError):
    pass


_DATA_RE = re.compile(r"#\s*data\s*```json\s*(.*?)\s*```", re.S)


def _section_re(names: tuple[str, ...]) -> re.Pattern:
    return re.compile(r"^#[ \t]*(" + "|".join(re.escape(n) for n in names) + r")[ \t]*$", re.M)


def _markdown_models() -> dict[str, type]:
    return {
        mapper.class_.__tablename__: mapper.class_
        for mapper in Base.registry.mappers
        if issubclass(mapper.class_, MarkdownBase) and mapper.class_ is not MarkdownBase
    }


def _parse(content: str, names: tuple[str, ...]) -> tuple[dict, dict[str, str]]:
    sections = {name: "" for name in names}
    data_match = _DATA_RE.search(content)
    if not data_match:
        sections[names[0]] = content.rstrip("\n")
        return {}, sections
    data = json.loads(data_match.group(1))

    rest = content[data_match.end():]
    # 同じ見出しが本文中に再び出ても節の切れ目にしない(最初の一つだけを見出しとして扱う)
    heads = []
    for match in _section_re(names).finditer(rest):
        if match.group(1) not in {name for name, _ in heads}:
            heads.append((match.group(1), match))
    for index, (name, match) in enumerate(heads):
        stop = heads[index + 1][1].start() if index + 1 < len(heads) else len(rest)
        sections[name] = rest[match.end():stop].strip("\n")
    return data, sections


def _upsert(
    session, model: type, columns: set[str], stamp_columns: set[str],
    confirm_columns: set[str], path: str, directory_path: str | None, content: str, manifest: Manifest,
    parent_id: int | None = None,
) -> tuple[object, bool]:
    """md を一件 db へ入れる。db 側も前回の同期から変わっていたら、衝突として True を返す。

    `parent_id` は親の md の下(本文のファイルなら隣)に置くモデルの、置き場所から決まる親の id。`# data` より勝つ。
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    if model.MARKDOWN_OWN_DIRECTORY and _is_record(path):
        # 名前はディレクトリが持つ
        stem = os.path.basename(os.path.dirname(path))
    row_id, stem_values = model.parse_markdown_stem(stem)

    if model.BODY_FILE_EXTENSION:
        data, sections = {}, {"text": content.rstrip("\n")}
    else:
        data, sections = _parse(content, model.TEXT_SECTIONS)
    data_id = data.pop("id", None)
    if row_id is None and data_id is not None:
        row_id = int(data_id)
    data["directory_path"] = directory_path
    children = {name: data.pop(name) for name in model.CHILD_LISTS if name in data}
    # `# data` にある欄はそれが勝つ。名前は `# data` に無い欄(filename や、手書き md の start/end)だけ埋める
    data.update({k: v for k, v in stem_values.items() if k not in data})
    parent = export_db.parent_of(model)
    if parent is not None:
        if parent_id is not None:
            data[parent[1]] = parent_id
        elif row_id is None:
            raise ImportDbError(
                f"{path}: 親の {parent[0].__tablename__} の md(同じ名前で .md の付いたもの)が隣に無い")
    if model.BODY_FILE_EXTENSION and row_id is None:
        # 親一行につき一行なので、その親の行があれば直す
        row_id = session.scalar(select(model.id).where(getattr(model, parent[1]) == parent_id))

    unknown = set(data) - columns
    if unknown:
        raise ImportDbError(f"{path}: スキーマに無い欄 {sorted(unknown)}")

    values = {}
    for key, value in data.items():
        if key in stamp_columns and value not in (None, ""):
            value = Stamp.parse(value)
        elif key in confirm_columns and value not in (None, ""):
            # 三段にする前の `true` / `false` の md も、そのまま読める
            value = parse_confirm_status(value)
        values[key] = value
    values.update(sections)

    row = session.get(model, row_id) if row_id is not None else None
    entry = manifest.get(path)
    conflict = False
    if entry is not None and entry["table"] == model.__tablename__ and entry["id"] == row_id:
        conflict = row is None or digest(export_db.render_row(model, row)) != entry["db"]
    # md 名は前回の書き出し時の名前のままなので、`# data` で名前を直した md は直す前の名前と比べる
    default_filenames = {row.default_filename()} if row is not None else set()
    if model is Idea and not values.get("kind", row.kind if row is not None else None):
        values["kind"] = idea_kind.judge(session, values.get("name"), values.get("text"), directory_path, ai_client)
    if row is None:
        values.update({key: "" for key in _required_texts(model) if values.get(key) is None})
        row = model(**values)
        session.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    for name, items in children.items():
        try:
            load_children(row, name, items)
        except ChildListError as error:
            raise ImportDbError(f"{path}: {error}") from error
    default_filenames.add(row.default_filename())
    # 名前から自動で付く部分(人物名など)は filename に残さない。名前が変わったら md 名も追従する
    if row.filename is not None and row.filename in default_filenames:
        row.filename = None
    session.flush()
    rendered = export_db.render_row(model, row)
    if row_id is None and not model.BODY_FILE_EXTENSION and not model.MARKDOWN_OWN_DIRECTORY:
        # 採番した id を md 側にも残す(名前か `# data` のどちらかに入る)
        os.remove(path)
        path = os.path.join(os.path.dirname(path), row.markdown_name)
        export_db._write(path, rendered)
        content = rendered
    manifest.set(path, model.__tablename__, row.id, digest(content), digest(rendered))
    return row, conflict


def _required_texts(model: type) -> list[str]:
    """空にできない文字列の列。md に無ければ、足す行は空文字で入れる。"""
    return [column.key for column in model.__table__.columns
            if not column.nullable and not column.primary_key and isinstance(column.type, String)
            and column.default is None and column.server_default is None]


def _fill_missing_parents(root: str, manifest: Manifest) -> None:
    """手で足した本文のファイルに、同じ名前の md(話)が無ければ空の md を、そのディレクトリに作品の md(`0_`)が
    無ければディレクトリ名で空の作品の md を置く。置いた md は、ほかの手で足した md と同じく取り込まれる。
    テーブルのディレクトリの直下は作品のディレクトリではないので、何も置かない。
    """
    models = export_db._markdown_models()
    for top in export_db._top_models(models):
        table_dir = os.path.normpath(os.path.join(root, top.__tablename__))
        bodies = tuple(extension for extension in export_db.file_extensions(top, models) if extension != ".md")
        if not bodies or not top.MARKDOWN_OWN_DIRECTORY:
            continue
        for dirpath, _dirnames, filenames in os.walk(table_dir):
            if os.path.normpath(dirpath) == table_dir:
                continue
            for filename in filenames:
                path = os.path.normpath(os.path.join(dirpath, filename))
                if not filename.endswith(bodies) or not manifest.edited(path, read_text(path)):
                    continue
                companion = _companion(path)
                if os.path.exists(companion):
                    continue
                if _companion(companion) is None:
                    export_db._write(os.path.join(dirpath, f"{RECORD_PREFIX}{os.path.basename(dirpath)}.md"), "")
                export_db._write(companion, "")


def _is_record(path: str) -> bool:
    return path.endswith(".md") and os.path.basename(path).startswith(RECORD_PREFIX)


def _companion(path: str) -> str | None:
    """親の md のパス。md なら同じディレクトリで先頭に並ぶ md(`0_` で始まる)、本文のファイルなら拡張子を .md にしたもの。"""
    stem, extension = os.path.splitext(path)
    if extension != ".md":
        return stem + ".md"
    if _is_record(path):
        return None
    directory = os.path.dirname(path)
    records = sorted(name for name in os.listdir(directory) if _is_record(name))
    return os.path.join(directory, records[0]) if records else None


def _model_of(path: str, top: type, manifest: Manifest, expected: dict,
              child_of: dict[tuple[type, str], type]) -> type | None:
    """置き場所から、ファイルがどのテーブルの行かを決める。同じディレクトリに `0_` で始まる md(親)があれば、その子のテーブル。
    本文のファイルは、隣の同じ名前の md のテーブルの子。決まらない本文のファイルは None。
    """
    if path in expected:
        return expected[path][0]
    entry = manifest.get(path)
    models = _markdown_models()
    if entry is not None and entry["table"] in models:
        return models[entry["table"]]
    extension = os.path.splitext(path)[1]
    companion = _companion(path)
    if companion is not None and os.path.isfile(companion):
        parent = _model_of(companion, top, manifest, expected, child_of)
        if (parent, extension) in child_of:
            return child_of[(parent, extension)]
    return top if extension == ".md" else None


def _edited_files(root: str, manifest: Manifest, expected: dict) -> list[tuple[type, str, str | None, str]]:
    """親の md の下に置くモデルの md は、`directory_path` を持たない(None で返す)。
    自分のディレクトリに置く md の `directory_path` は、そのディレクトリの一つ上。

    同じディレクトリの中では親の md(`0_` で始まる)が先に並ぶ。
    """
    models = export_db._markdown_models()
    child_of = {(export_db.parent_of(model)[0], model.BODY_FILE_EXTENSION or ".md"): model
                for model in models if export_db.parent_of(model)}
    edited = []
    for top in export_db._top_models(models):
        table_dir = os.path.join(root, top.__tablename__)
        extensions = export_db.file_extensions(top, models)
        for dirpath, dirnames, filenames in os.walk(table_dir):
            dirnames.sort()
            relative = os.path.relpath(dirpath, table_dir)
            # 親の md を先に取り込んで、子の親の id を決めておく。本文のファイルは隣の md より後に並べる
            for filename in sorted(filenames, key=lambda name: (not name.endswith(".md"), name)):
                if not filename.endswith(extensions):
                    continue
                path = os.path.normpath(os.path.join(dirpath, filename))
                content = read_text(path)
                if not manifest.edited(path, content):
                    continue
                model = _model_of(path, top, manifest, expected, child_of)
                if model is None:
                    raise ImportDbError(f"{path}: 同じ名前の、本文を持てる md が隣に無い")
                directory_path = None
                if model is top:
                    placed = os.path.dirname(relative) if model.MARKDOWN_OWN_DIRECTORY and _is_record(path) else relative
                    directory_path = None if placed in (".", "") else placed.replace(os.sep, "/")
                edited.append((model, path, directory_path, content))
    return edited


def _parent_id(model: type, path: str, manifest: Manifest, imported: dict[str, int]) -> int | None:
    parent = export_db.parent_of(model)
    if parent is None:
        return None
    companion = _companion(path)
    if companion is None:
        return None
    if companion in imported:
        return imported[companion]
    entry = manifest.get(companion)
    if entry is not None and entry["table"] == parent[0].__tablename__:
        return entry["id"]
    return None


def _removed_rows(session, manifest: Manifest) -> list[tuple[type, str, object]]:
    """手で消された md と、その行。動かしただけの md(同じ行を別の md が持つ)は含めない。"""
    models = _markdown_models()
    missing = manifest.missing()
    missing_keys = {manifest.key(path) for path in missing}
    kept = {(entry["table"], entry["id"]) for key, entry in manifest.entries.items()
            if key not in missing_keys}
    removed = []
    for path in missing:
        entry = manifest.get(path)
        model = models.get(entry["table"])
        if model is None or (entry["table"], entry["id"]) in kept:
            continue
        row = session.get(model, entry["id"])
        if row is not None:
            removed.append((model, path, row))
    return removed


def _delete_rows(session, removed: list[tuple[type, str, object]]) -> None:
    ids: dict[type, set[int]] = {}
    for model, _path, row in removed:
        ids.setdefault(model, set()).add(row.id)
    tables = {model.__table__: model for model in _markdown_models().values()}

    for model, deleting in ids.items():
        for mapper in Base.registry.mappers:
            other = mapper.class_
            if getattr(other, "__table__", None) is None:
                continue
            for column in other.__table__.columns:
                if not any(fk.column.table is model.__table__ for fk in column.foreign_keys):
                    continue
                if other.__table__ not in tables:
                    # md に出さない行(要約・中間テーブル・子の行)は、元の行と一緒に消す
                    session.execute(delete(other).where(column.in_(deleting)))
                    continue
                left = session.scalars(
                    select(other.id).where(column.in_(deleting))
                    .where(other.id.not_in(ids.get(other, set())))).all()
                if left:
                    raise ImportDbError(
                        f"消された md の行 {model.__tablename__} {sorted(deleting)} を、"
                        f"残っている {other.__tablename__} {sorted(left)} が {column.key} で指している。"
                        "そちらの md も消すか、指す先を直してから同期する")
    for model, deleting in ids.items():
        session.execute(delete(model).where(model.id.in_(deleting)))


def _backup() -> None:
    date_str = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = f"backup/{date_str}.db.bk"
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    shutil.copy(NOVEL_DB_PATH, backup_path)


def import_changes(session, root: str, manifest: Manifest) -> dict:
    """前回の同期より後に手で直された(または足された)md だけを db へ入れ、手で消された md の行を db から消す。
    commit はしない。

    db 側も同じ行を直していたら md の方を勝たせ、その md を `conflicts` に返す。
    """
    expected, _counts = export_db._expected(session, root, export_db._markdown_models())
    _fill_missing_parents(root, manifest)
    edited = []
    for model, path, directory_path, content in _edited_files(root, manifest, expected):
        # 台帳が無い・古いだけで、db と同じ中身・同じ置き場所の md(git で両方そろって入ってきたものなど)は台帳に載せるだけにする
        known = expected.get(path)
        if known is not None and known[0] is model and known[2] == content:
            manifest.set(path, model.__tablename__, known[1].id, digest(content), digest(content))
        else:
            edited.append((model, path, directory_path, content))
    if edited:
        _backup()
    counts: dict[str, int] = {}
    conflicts = []
    imported: dict[str, int] = {}
    for model, path, directory_path, content in edited:
        columns = {column.key for column in model.__table__.columns}
        stamp_columns = {
            column.key for column in model.__table__.columns
            if isinstance(column.type, StampType)
        }
        confirm_columns = {
            column.key for column in model.__table__.columns
            if isinstance(column.type, ConfirmStatusType)
        }
        row, conflict = _upsert(session, model, columns, stamp_columns, confirm_columns, path, directory_path,
                                content, manifest, _parent_id(model, path, manifest, imported))
        imported[path] = row.id
        if conflict:
            conflicts.append(path)
        counts[model.__tablename__] = counts.get(model.__tablename__, 0) + 1

    # 動かしただけの md を見分けるため、消された md は動かした先を台帳に載せてから探す
    removed = _removed_rows(session, manifest)
    if removed and not edited:
        _backup()
    for model, path, row in removed:
        if digest(export_db.render_row(model, row)) != manifest.get(path)["db"]:
            conflicts.append(path)
    _delete_rows(session, removed)
    for _model, path, _row in removed:
        manifest.drop(path)
    return {"counts": counts, "conflicts": conflicts, "deleted": [path for _model, path, _row in removed]}


def import_db(root: str = WORLDS_ROOT) -> dict[str, int]:
    with locked(root):
        manifest = Manifest(root)
        with get_novel_session() as session:
            result = import_changes(session, root, manifest)
            session.commit()
        manifest.save()
    return result["counts"]
