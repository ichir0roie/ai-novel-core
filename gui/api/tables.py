#!/usr/bin/env python3
"""GUI が扱うテーブル。本文を持つテーブル(`ContentBase`)を、確定・修正の入口と組にして持つ。

GUI からの書き込みは、入口の `execute(s)`(検証と db への書き込みだけ)を呼ぶ。
`run()` は呼ばない。`run()` は確定のあとに AI(`claude -p`)で要約・ミーム・検証を作る段を持ち、
GUI の一回の操作で待てる長さではないため。その分は `RefreshGeneratedContent` が後でまとめて拾う。
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from data_access_logic.character.commit_character import CommitCharacter
from data_access_logic.character.commit_character_relation import CommitCharacterRelation
from data_access_logic.character.commit_character_skill import CommitCharacterSkill
from data_access_logic.character.form import (
    CharacterCreateForm, CharacterRelationCreateForm, CharacterRelationUpdateForm, CharacterSkillCreateForm,
    CharacterSkillUpdateForm, CharacterUpdateForm,
)
from data_access_logic.character.record import CharacterRecord, CharacterRelationRecord, CharacterSkillRecord
from data_access_logic.character.update_character import UpdateCharacter
from data_access_logic.character.update_character_relation import UpdateCharacterRelation
from data_access_logic.character.update_character_skill import UpdateCharacterSkill
from data_access_logic.episode.commit_episode import CommitEpisode
from data_access_logic.episode.form import EpisodeCommitForm, EpisodeCreateForm
from data_access_logic.entrypoint import UnknownRecordError
from data_access_logic.episode.record import EpisodeRecord
from data_access_logic.event.commit_event import CommitEvent
from data_access_logic.event.form import EventCreateForm, EventUpdateForm
from data_access_logic.event.record import EventRecord
from data_access_logic.event.update_event import UpdateEvent
from data_access_logic.idea.commit_idea import CommitIdea
from data_access_logic.idea.form import IdeaCreateForm, IdeaUpdateForm
from data_access_logic.idea.record import IdeaRecord
from data_access_logic.idea.update_idea import UpdateIdea
from data_access_logic.location.commit_location import CommitLocation
from data_access_logic.location.form import LocationCreateForm, LocationUpdateForm
from data_access_logic.location.record import LocationRecord
from data_access_logic.location.update_location import UpdateLocation
from data_access_logic.material import Material
from data_access_logic.meme.commit_meme import CommitMeme
from data_access_logic.meme.form import MemeCreateForm, MemeUpdateForm
from data_access_logic.meme.record import MemeRecord
from data_access_logic.meme.update_meme import UpdateMeme
from data_access_logic.oracle.commit_oracle import CommitOracle
from data_access_logic.oracle.form import OracleCreateForm, OracleUpdateForm
from data_access_logic.oracle.record import OracleRecord
from data_access_logic.oracle.update_oracle import UpdateOracle
from data_access_logic.story.commit_story import CommitStory
from data_access_logic.story.form import StoryCreateForm, StoryUpdateForm
from data_access_logic.story.record import StoryRecord
from data_access_logic.story.update_story import UpdateStory
from data_access_logic.style_preference.commit_style_preference import CommitStylePreference
from data_access_logic.style_preference.form import StylePreferenceCreateForm, StylePreferenceUpdateForm
from data_access_logic.style_preference.record import StylePreferenceRecord
from data_access_logic.style_preference.update_style_preference import UpdateStylePreference
from db.schema import (
    Character, CharacterRelation, CharacterSkill, Episode, Event, Idea, Location, Meme, Oracle, Story, StylePreference,
)


@dataclass(frozen=True)
class TableSpec:
    name: str
    model: type
    creator: type
    updater: type
    # 入口の引数。GUI から来た dict をこれに読み込んで渡す
    create_form: type[BaseModel]
    update_form: type[BaseModel]
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


TABLES: tuple[TableSpec, ...] = (
    TableSpec("story", Story, CommitStory, UpdateStory, StoryCreateForm, StoryUpdateForm, StoryRecord,
              ("name", "text"), sort="display_order", order="asc"),
    TableSpec("episode", Episode, CommitEpisode, CommitEpisode, EpisodeCreateForm, EpisodeCommitForm,
              EpisodeRecord, ("title", "plot_text"), sort="start", order="desc"),
    TableSpec("character", Character, CommitCharacter, UpdateCharacter, CharacterCreateForm,
              CharacterUpdateForm, CharacterRecord, ("name", "appearance", "text", "meme", "principle", "plot", "histories.description")),
    TableSpec("character_relation", CharacterRelation, CommitCharacterRelation,
              UpdateCharacterRelation, CharacterRelationCreateForm, CharacterRelationUpdateForm,
              CharacterRelationRecord, ("relation", "text", "histories.description")),
    TableSpec("character_skill", CharacterSkill, CommitCharacterSkill, UpdateCharacterSkill, CharacterSkillCreateForm,
              CharacterSkillUpdateForm, CharacterSkillRecord, ("name", "text", "histories.description")),
    TableSpec("event", Event, CommitEvent, UpdateEvent, EventCreateForm, EventUpdateForm, EventRecord,
              ("name", "text")),
    TableSpec("location", Location, CommitLocation, UpdateLocation, LocationCreateForm, LocationUpdateForm,
              LocationRecord, ("name", "text"), tree_parent_column="parent_id"),
    TableSpec("idea", Idea, CommitIdea, UpdateIdea, IdeaCreateForm, IdeaUpdateForm, IdeaRecord,
              ("name", "text"), tree_parent_column="parent_idea_id"),
    TableSpec("meme", Meme, CommitMeme, UpdateMeme, MemeCreateForm, MemeUpdateForm, MemeRecord,
              ("text",)),
    TableSpec("oracle", Oracle, CommitOracle, UpdateOracle, OracleCreateForm, OracleUpdateForm,
              OracleRecord, ("title", "text")),
    TableSpec("style_preference", StylePreference, CommitStylePreference, UpdateStylePreference,
              StylePreferenceCreateForm, StylePreferenceUpdateForm, StylePreferenceRecord, ("text",),
              order="asc"),
)

TABLE_BY_NAME: dict[str, TableSpec] = {spec.name: spec for spec in TABLES}


def spec_of(table: str) -> TableSpec:
    spec = TABLE_BY_NAME.get(table)
    if spec is None:
        raise UnknownRecordError(f"GUI で扱わないテーブル: {table}")
    return spec
