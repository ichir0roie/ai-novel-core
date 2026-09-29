#!/usr/bin/env python3
"""GUI が扱うテーブル。本文を持つテーブル(`TextBase`)を、確定・修正の入口と組にして持つ。

GUI からの書き込みは、入口の `execute(session)`(検証と db への書き込みだけ)を呼ぶ。
`run()` は呼ばない。`run()` は確定のあとに AI(`claude -p`)で要約・ミーム・検証を作る段を持ち、
GUI の一回の操作で待てる長さではないため。その分は `RefreshGeneratedContent` が後でまとめて拾う。
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy.orm import selectinload

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
from ai.claude_code.interface.story.commit_episode import CommitEpisode
from ai.claude_code.interface.story.commit_story import CommitStory
from ai.claude_code.interface.story.update_story import UpdateStory
from data_access_logic.character.form import (
    CharacterCreateForm, CharacterRelationCreateForm, CharacterRelationUpdateForm, CharacterUpdateForm,
)
from data_access_logic.character.record import CharacterRecord, CharacterRelationRecord
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.event.form import EventCreateForm, EventUpdateForm
from data_access_logic.event.record import EventRecord
from data_access_logic.idea.form import IdeaCreateForm, IdeaUpdateForm
from data_access_logic.idea.record import IdeaRecord
from data_access_logic.location.form import LocationCreateForm, LocationUpdateForm
from data_access_logic.location.record import LocationRecord
from data_access_logic.material import Material
from data_access_logic.meme.form import MemeCreateForm, MemeUpdateForm
from data_access_logic.meme.record import MemeRecord
from data_access_logic.oracle.form import OracleCreateForm, OracleUpdateForm
from data_access_logic.oracle.record import OracleRecord
from data_access_logic.story.form import StoryCreateForm, StoryUpdateForm
from data_access_logic.story.record import StoryRecord
from db.schema import (
    Character, CharacterRelation, Episode, Event, Idea, Location, Meme, Oracle, Story,
)


@dataclass(frozen=True)
class TableSpec:
    name: str
    label: str
    model: type
    creator: type
    updater: type
    # 入口の引数。GUI から来た dict をこれに読み込んで渡す
    create_form: type[BaseModel]
    update_form: type[BaseModel]
    # 画面に返す行の形
    record_model: type[Material]
    # 一覧・選択肢で行を呼ぶ名前にする列。空なら text の先頭
    label_column: str | None
    # 一覧の検索(部分一致)で見る列
    search_columns: tuple[str, ...]
    # `confirmed` を持ち、レビュー画面の対象になるか
    reviewable: bool = False
    # 一覧の既定の並び(列名と向き)
    sort: str = "id"
    order: str = "desc"
    # 自己参照で親子を持つ列(あれば)。選択肢(`/options`)にこの列の値を添えて、
    # GUI のプルダウンをツリー表示にする(`ReferenceTreeSelect`)
    tree_parent_column: str | None = None
    # `record_model` に詰めるのに要る、noload のリレーションの読み方(当事者・登場人物)
    load_options: tuple = ()


TABLES: tuple[TableSpec, ...] = (
    TableSpec("story", "作品", Story, CommitStory, UpdateStory, StoryCreateForm, StoryUpdateForm, StoryRecord,
              "name", ("name", "text")),
    TableSpec("episode", "話", Episode, CommitEpisode, CommitEpisode, EpisodeCommitForm, EpisodeCommitForm,
              EpisodeRecord, "title", ("title", "key"), sort="start", order="asc",
              load_options=(selectinload(Episode.episode_characters),)),
    TableSpec("character", "人物", Character, CommitCharacter, UpdateCharacter, CharacterCreateForm,
              CharacterUpdateForm, CharacterRecord, "name", ("name", "text"),
              reviewable=True),
    TableSpec("character_relation", "人物相関", CharacterRelation, CommitCharacterRelation,
              UpdateCharacterRelation, CharacterRelationCreateForm, CharacterRelationUpdateForm,
              CharacterRelationRecord, "relation", ("relation", "text")),
    TableSpec("event", "出来事", Event, CommitEvent, UpdateEvent, EventCreateForm, EventUpdateForm, EventRecord,
              "name", ("name", "text"), reviewable=True,
              load_options=(selectinload(Event.event_characters),)),
    TableSpec("location", "場所", Location, CommitPlace, UpdatePlace, LocationCreateForm, LocationUpdateForm,
              LocationRecord, "name", ("name", "text"), tree_parent_column="parent_id"),
    TableSpec("idea", "アイデア", Idea, CommitIdea, UpdateIdea, IdeaCreateForm, IdeaUpdateForm, IdeaRecord,
              "name", ("name", "text"), reviewable=True, tree_parent_column="parent_idea_id"),
    TableSpec("meme", "ミーム", Meme, CommitMeme, UpdateMeme, MemeCreateForm, MemeUpdateForm, MemeRecord,
              None, ("text",), reviewable=True),
    TableSpec("oracle", "覚え書き", Oracle, CommitOracle, UpdateOracle, OracleCreateForm, OracleUpdateForm,
              OracleRecord, "title", ("title", "text")),
)

TABLE_BY_NAME: dict[str, TableSpec] = {spec.name: spec for spec in TABLES}


def spec_of(table: str) -> TableSpec:
    spec = TABLE_BY_NAME.get(table)
    if spec is None:
        raise KeyError(f"GUI で扱わないテーブル: {table}")
    return spec
