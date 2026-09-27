#!/usr/bin/env python3
"""GUI が扱うテーブル。本文を持つテーブル(`TextBase`)を、確定・修正の入口と組にして持つ。

GUI からの書き込みは、入口の `execute(session)`(検証と db への書き込みだけ)を呼ぶ。
`run()` は呼ばない。`run()` は確定のあとに AI(`claude -p`)で要約・ミーム・検証を作る段を持ち、
GUI の一回の操作で待てる長さではないため。その分は `RefreshGeneratedContent` が後でまとめて拾う。
"""
from __future__ import annotations

from dataclasses import dataclass

from ai.claude_code.interface.randomizer.commit_character import CommitCharacter
from ai.claude_code.interface.randomizer.commit_character_relation import CommitCharacterRelation
from ai.claude_code.interface.randomizer.commit_event import CommitEvent
from ai.claude_code.interface.randomizer.commit_idea import CommitIdea
from ai.claude_code.interface.randomizer.commit_meme import CommitMeme
from ai.claude_code.interface.randomizer.commit_oracle import CommitOracle
from ai.claude_code.interface.randomizer.commit_place import CommitPlace
from ai.claude_code.interface.randomizer.update_character import UpdateCharacter
from ai.claude_code.interface.randomizer.update_character_relation import UpdateCharacterRelation
from ai.claude_code.interface.randomizer.update_event import UpdateEvent
from ai.claude_code.interface.randomizer.update_idea import UpdateIdea
from ai.claude_code.interface.randomizer.update_meme import UpdateMeme
from ai.claude_code.interface.randomizer.update_oracle import UpdateOracle
from ai.claude_code.interface.randomizer.update_place import UpdatePlace
from ai.claude_code.interface.story.commit_plot import CommitPlot
from ai.claude_code.interface.story.commit_story import CommitStory
from ai.claude_code.interface.story.update_story import UpdateStory
from db.schema import (
    Character, CharacterRelation, Event, Idea, Location, Meme, Oracle, Plot, Story,
)


@dataclass(frozen=True)
class TableSpec:
    name: str
    label: str
    model: type
    creator: type
    updater: type
    # 一覧・選択肢で行を呼ぶ名前にする列。空なら text の先頭
    label_column: str | None
    # 一覧の検索(部分一致)で見る列
    search_columns: tuple[str, ...]
    # 入口が列の外で受け取る欄(参加者の id など)。列の検証には掛けず、そのまま入口へ渡す
    extra_fields: tuple[str, ...] = ()
    # `confirmed` を持ち、レビュー画面の対象になるか
    reviewable: bool = False
    # 一覧の既定の並び(列名と向き)
    sort: str = "id"
    order: str = "desc"


TABLES: tuple[TableSpec, ...] = (
    TableSpec("story", "作品", Story, CommitStory, UpdateStory, "name", ("name", "text")),
    TableSpec("plot", "話", Plot, CommitPlot, CommitPlot, "title", ("title", "key"),
              extra_fields=("text",), sort="start", order="asc"),
    TableSpec("character", "人物", Character, CommitCharacter, UpdateCharacter, "name", ("name", "text"),
              extra_fields=("place_id",)),
    TableSpec("character_relation", "人物相関", CharacterRelation, CommitCharacterRelation,
              UpdateCharacterRelation, "relation", ("relation", "text")),
    TableSpec("event", "出来事", Event, CommitEvent, UpdateEvent, "name", ("name", "text"),
              extra_fields=("character_ids",)),
    TableSpec("location", "場所", Location, CommitPlace, UpdatePlace, "name", ("name", "text")),
    TableSpec("idea", "アイデア", Idea, CommitIdea, UpdateIdea, "name", ("name", "text"), reviewable=True),
    TableSpec("meme", "ミーム", Meme, CommitMeme, UpdateMeme, None, ("text",), reviewable=True),
    TableSpec("oracle", "覚え書き", Oracle, CommitOracle, UpdateOracle, "title", ("title", "text")),
)

TABLE_BY_NAME: dict[str, TableSpec] = {spec.name: spec for spec in TABLES}


def spec_of(table: str) -> TableSpec:
    spec = TABLE_BY_NAME.get(table)
    if spec is None:
        raise KeyError(f"GUI で扱わないテーブル: {table}")
    return spec
