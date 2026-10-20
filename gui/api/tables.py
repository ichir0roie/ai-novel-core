#!/usr/bin/env python3
"""GUI が扱うテーブル。本文を持つテーブル(`ContentBase`)を、確定・修正の入口と組にして持つ。

GUI からの書き込みは、入口の `execute(s)`(検証と db への書き込みだけ)を呼ぶ。
`run()` は呼ばない。`run()` は確定のあとに AI(`claude -p`)で要約・ミーム・検証を作る段を持ち、
GUI の一回の操作で待てる長さではないため。要約・アンチミームの分は `RefreshGeneratedContent` が後でまとめて拾う。

読む側(行の形・検索・並び)は `TABLES` に先に持ち、書く側(確定・修正の入口と引数のモデル)は `writer_of` が
その表を書くときにだけ import する。確定・修正の入口は流れや AI の段まで連れてきて重く、一件を読むだけの要求
(Lambda のコールドスタートの最初の要求)に、全部の表の分を読み込ませないため。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

from pydantic import BaseModel

from data_access_logic.character.record import CharacterRecord, CharacterRelationRecord, CharacterSkillRecord
from data_access_logic.entrypoint import UnknownRecordError
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.event.record import EventRecord
from data_access_logic.idea.record import IdeaRecord
from data_access_logic.location.record import LocationRecord
from data_access_logic.material import Material
from data_access_logic.meme.record import MemeRecord
from data_access_logic.oracle.record import OracleRecord
from data_access_logic.story.record import StoryRecord
from data_access_logic.style_preference.record import StylePreferenceRecord
from db.schema import (
    Character, CharacterRelation, CharacterSkill, Episode, Event, Idea, Location, Meme, Oracle, Story, StylePreference,
)


@dataclass(frozen=True)
class TableSpec:
    name: str
    model: type
    # 画面に返す行の形
    record_model: type[Material]
    # 一覧の検索(部分一致)で見る列
    search_columns: tuple[str, ...]
    # 一覧の既定の並び(列名と向き)
    sort: str = "id"
    order: str = "desc"
    # 自己参照で親子を持つ列(あれば)。選択肢(`/options`)にこの列の値を添えて、
    # GUI のプルダウンをツリー表示にする(`ReferenceTreeSelect`)
    tree_parent_column: str | None = None


@dataclass(frozen=True)
class TableWriter:
    creator: type
    updater: type
    # 入口の引数。GUI から来た dict をこれに読み込んで渡す
    create_form: type[BaseModel]
    update_form: type[BaseModel]


TABLES: tuple[TableSpec, ...] = (
    TableSpec("story", Story, StoryRecord, ("name", "text"), sort="display_order", order="asc"),
    TableSpec("episode", Episode, EpisodeRecord, ("title", "plot_text"), sort="start", order="desc"),
    TableSpec("character", Character, CharacterRecord,
              ("name", "appearance", "text", "meme", "principle", "plot", "histories.description")),
    TableSpec("character_relation", CharacterRelation, CharacterRelationRecord, ("relation", "text", "histories.description")),
    TableSpec("character_skill", CharacterSkill, CharacterSkillRecord, ("name", "text", "histories.description")),
    TableSpec("event", Event, EventRecord, ("name", "text")),
    TableSpec("location", Location, LocationRecord, ("name", "text"), tree_parent_column="parent_id"),
    TableSpec("idea", Idea, IdeaRecord, ("name", "text"), tree_parent_column="parent_idea_id"),
    TableSpec("meme", Meme, MemeRecord, ("text",)),
    TableSpec("oracle", Oracle, OracleRecord, ("title", "text")),
    TableSpec("style_preference", StylePreference, StylePreferenceRecord, ("text",), order="asc"),
)

TABLE_BY_NAME: dict[str, TableSpec] = {spec.name: spec for spec in TABLES}


def spec_of(table: str) -> TableSpec:
    spec = TABLE_BY_NAME.get(table)
    if spec is None:
        raise UnknownRecordError(f"GUI で扱わないテーブル: {table}")
    return spec


def _story() -> TableWriter:
    from data_access_logic.story.commit_story import CommitStory
    from data_access_logic.story.form import StoryCreateForm, StoryUpdateForm
    from data_access_logic.story.update_story import UpdateStory
    return TableWriter(CommitStory, UpdateStory, StoryCreateForm, StoryUpdateForm)


def _episode() -> TableWriter:
    from data_access_logic.episode.commit_episode import CommitEpisode
    from data_access_logic.episode.form import EpisodeCommitForm, EpisodeCreateForm
    return TableWriter(CommitEpisode, CommitEpisode, EpisodeCreateForm, EpisodeCommitForm)


def _character() -> TableWriter:
    from data_access_logic.character.commit_character import CommitCharacter
    from data_access_logic.character.form import CharacterCreateForm, CharacterUpdateForm
    from data_access_logic.character.update_character import UpdateCharacter
    return TableWriter(CommitCharacter, UpdateCharacter, CharacterCreateForm, CharacterUpdateForm)


def _character_relation() -> TableWriter:
    from data_access_logic.character.commit_character_relation import CommitCharacterRelation
    from data_access_logic.character.form import CharacterRelationCreateForm, CharacterRelationUpdateForm
    from data_access_logic.character.update_character_relation import UpdateCharacterRelation
    return TableWriter(CommitCharacterRelation, UpdateCharacterRelation, CharacterRelationCreateForm,
                       CharacterRelationUpdateForm)


def _character_skill() -> TableWriter:
    from data_access_logic.character.commit_character_skill import CommitCharacterSkill
    from data_access_logic.character.form import CharacterSkillCreateForm, CharacterSkillUpdateForm
    from data_access_logic.character.update_character_skill import UpdateCharacterSkill
    return TableWriter(CommitCharacterSkill, UpdateCharacterSkill, CharacterSkillCreateForm, CharacterSkillUpdateForm)


def _event() -> TableWriter:
    from data_access_logic.event.commit_event import CommitEvent
    from data_access_logic.event.form import EventCreateForm, EventUpdateForm
    from data_access_logic.event.update_event import UpdateEvent
    return TableWriter(CommitEvent, UpdateEvent, EventCreateForm, EventUpdateForm)


def _location() -> TableWriter:
    from data_access_logic.location.commit_location import CommitLocation
    from data_access_logic.location.form import LocationCreateForm, LocationUpdateForm
    from data_access_logic.location.update_location import UpdateLocation
    return TableWriter(CommitLocation, UpdateLocation, LocationCreateForm, LocationUpdateForm)


def _idea() -> TableWriter:
    from data_access_logic.idea.commit_idea import CommitIdea
    from data_access_logic.idea.form import IdeaCreateForm, IdeaUpdateForm
    from data_access_logic.idea.update_idea import UpdateIdea
    return TableWriter(CommitIdea, UpdateIdea, IdeaCreateForm, IdeaUpdateForm)


def _meme() -> TableWriter:
    from data_access_logic.meme.commit_meme import CommitMeme
    from data_access_logic.meme.form import MemeCreateForm, MemeUpdateForm
    from data_access_logic.meme.update_meme import UpdateMeme
    return TableWriter(CommitMeme, UpdateMeme, MemeCreateForm, MemeUpdateForm)


def _oracle() -> TableWriter:
    from data_access_logic.oracle.commit_oracle import CommitOracle
    from data_access_logic.oracle.form import OracleCreateForm, OracleUpdateForm
    from data_access_logic.oracle.update_oracle import UpdateOracle
    return TableWriter(CommitOracle, UpdateOracle, OracleCreateForm, OracleUpdateForm)


def _style_preference() -> TableWriter:
    from data_access_logic.style_preference.commit_style_preference import CommitStylePreference
    from data_access_logic.style_preference.form import StylePreferenceCreateForm, StylePreferenceUpdateForm
    from data_access_logic.style_preference.update_style_preference import UpdateStylePreference
    return TableWriter(CommitStylePreference, UpdateStylePreference, StylePreferenceCreateForm, StylePreferenceUpdateForm)


_WRITERS: dict[str, Callable[[], TableWriter]] = {
    "story": _story, "episode": _episode, "character": _character, "character_relation": _character_relation,
    "character_skill": _character_skill, "event": _event, "location": _location, "idea": _idea, "meme": _meme,
    "oracle": _oracle, "style_preference": _style_preference,
}


@cache
def writer_of(table: str) -> TableWriter:
    return _WRITERS[spec_of(table).name]()
