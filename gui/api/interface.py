#!/usr/bin/env python3
"""`data_access_logic/<領域>/` の入口を、API(`POST /api/interface/{id}`)と web のセッション(`web_session/flows.py`)から呼ぶ。

入口は id(`data_access_logic/readme.md` の表と同じ「領域.ファイル.クラス」)を下の固定の一覧に書き、呼ばれた入口のモジュールだけを
その時に import する。起動のときに入口を全部読み込まない(Lambda のコールドスタートで、全部の import を待たせない)。
入口を足したら id を一覧に足す。db だけの入口は `DB_ENTRANCES`、`claude -p` を回すもの(確定のあとに AI を回す `run()` を
持つ入口、AI を受け取る入口)は `CLAUDE_ENTRANCES`。足し忘れ・振り分けの誤りは `tests/api/test_static.py` が落とす。
`CLAUDE_ENTRANCES` は API からは呼ばせない(Claude のセッションが、手元は `show()`、web は `web_session/flows.py` で呼ぶ)。
"""
from __future__ import annotations

import importlib
import inspect
import typing
from functools import cache
from typing import Any

from pydantic import BaseModel, TypeAdapter

from data_access_logic.entrypoint import Entrypoint, UnknownRecordError

DB_ENTRANCES = frozenset({
    "character.add_knower.AddKnower",
    "character.append_history.AppendCharacterHistory",
    "character.append_relation_history.AppendRelationHistory",
    "character.append_skill_history.AppendSkillHistory",
    "character.commit_character.CommitCharacter",
    "character.commit_character_location.CommitCharacterLocation",
    "character.commit_character_relation.CommitCharacterRelation",
    "character.commit_character_skill.CommitCharacterSkill",
    "character.create_random_character.CreateRandomCharacter",
    "character.delete_character.DeleteCharacter",
    "character.delete_character_relation.DeleteCharacterRelation",
    "character.delete_character_skill.DeleteCharacterSkill",
    "character.list_character_relations.ListCharacterRelations",
    "character.list_characters.ListCharacters",
    "character.move_characters.MoveCharacters",
    "character.read_appearance.ReadAppearance",
    "character.read_character.ReadCharacter",
    "character.read_knowable_rows.ReadKnowableRows",
    "character.read_knowledge.ReadKnowledge",
    "character.read_known_ideas.ReadKnownIdeas",
    "character.read_known_rows.ReadKnownRows",
    "character.read_surroundings.ReadSurroundings",
    "character.update_character.UpdateCharacter",
    "character.update_character_location.UpdateCharacterLocation",
    "character.update_character_relation.UpdateCharacterRelation",
    "character.update_character_skill.UpdateCharacterSkill",
    "character.update_history.UpdateCharacterHistory",
    "character.update_knowledge.UpdateKnowledge",
    "character.update_relation_history.UpdateRelationHistory",
    "character.update_skill_history.UpdateSkillHistory",
    "episode.cast_episode.CastEpisode",
    "episode.delete_episode.DeleteEpisode",
    "episode.move_episodes.MoveEpisodes",
    "episode.read_character_episodes.ReadCharacterEpisodes",
    "episode.read_episode_casting.ReadEpisodeCasting",
    "episode.read_episode_texts.ReadEpisodeTexts",
    "episode.read_episodes.ReadEpisodes",
    "episode.refresh_mentions.RefreshMentions",
    "episode.revise_episode.ReviseEpisode",
    "episode.update_episodes.UpdateEpisodes",
    "episode_session.add_ideas.AddIdeas",
    "episode_session.read_knower_gaps.ReadKnowerGaps",
    "episode_session.read_stage.ReadStage",
    "event.create_random_event.CreateRandomEvent",
    "event.delete_event.DeleteEvent",
    "event.list_events.ListEvents",
    "event.read_events.ReadEvents",
    "event.update_events.UpdateEvents",
    "event_seed.update_event_seed.UpdateEventSeed",
    "expansion.add_conflict.AddConflict",
    "expansion.finish_expansion.FinishExpansion",
    "expansion.list_expansions.ListExpansions",
    "expansion.read_expansion.ReadExpansion",
    "expansion.resolve_conflict.ResolveConflict",
    "expansion.revert_expansion.RevertExpansion",
    "expansion.start_expansion.StartExpansion",
    "idea.append_history.AppendIdeaHistory",
    "idea.commit_idea.CommitIdea",
    "idea.delete_idea.DeleteIdea",
    "idea.merge_idea.MergeIdea",
    "idea.resolve_ideas.ResolveIdeas",
    "idea.search_ideas.SearchIdeas",
    "idea.update_history.UpdateIdeaHistory",
    "idea.update_idea.UpdateIdea",
    "location.append_history.AppendLocationHistory",
    "location.commit_location.CommitLocation",
    "location.create_random_location.CreateRandomLocation",
    "location.delete_location.DeleteLocation",
    "location.list_locations.ListLocations",
    "location.list_neighbors.ListNeighbors",
    "location.update_history.UpdateLocationHistory",
    "location.update_location.UpdateLocation",
    "meme.commit_meme.CommitMeme",
    "meme.delete_meme.DeleteMeme",
    "meme.draw_memes.DrawMemes",
    "meme.update_meme.UpdateMeme",
    "oracle.update_oracle.UpdateOracle",
    "review.list_pending_reviews.ListPendingReviews",
    "story.commit_story.CommitStory",
    "story.delete_story.DeleteStory",
    "story.list_stories.ListStories",
    "story.read_brief.ReadBrief",
    "story.read_cast.ReadCast",
    "story.start_story.StartStory",
    "story.update_stories.UpdateStories",
    "story.update_story.UpdateStory",
    "style_preference.commit_style_preference.CommitStylePreference",
    "style_preference.read_writing_style.ReadWritingStyle",
    "style_preference.update_style_preference.UpdateStylePreference",
    "world.search_world.SearchWorld",
})

CLAUDE_ENTRANCES = frozenset({
    "character.generate_character.GenerateCharacter",
    "character.generate_characters.GenerateCharacters",
    "episode.commit_episode.CommitEpisode",
    "episode.complete_plot.CompletePlot",
    "episode.generate_frame.GenerateFrame",
    "episode.read_episode_brief.ReadEpisodeBrief",
    "episode.refresh_voices.RefreshVoices",
    "event.commit_event.CommitEvent",
    "event.generate_event.GenerateEvent",
    "event.update_event.UpdateEvent",
    "event_seed.extract_event_seeds.ExtractEventSeeds",
    "expansion.act_character.ActCharacter",
    "fact_check.check_facts.CheckFacts",
    "meme.refresh_generated_content.RefreshGeneratedContent",
    "oracle.commit_oracle.CommitOracle",
})


class ClaudeEntranceForbidden(PermissionError):
    pass


@cache
def entrance_class(entrance_id: str) -> type[Entrypoint]:
    if entrance_id not in DB_ENTRANCES and entrance_id not in CLAUDE_ENTRANCES:
        raise UnknownRecordError(f"入口が無い: {entrance_id}")
    module_name, _, class_name = entrance_id.rpartition(".")
    return getattr(importlib.import_module(f"data_access_logic.{module_name}"), class_name)


def db_entrance_class(entrance_id: str) -> type[Entrypoint]:
    """API から呼べる入口(claude を叩かないもの)。"""
    if entrance_id in CLAUDE_ENTRANCES:
        raise ClaudeEntranceForbidden(
            f"{entrance_id} は claude コマンドを叩くので API からは呼べない。Claude のセッションから呼ぶ"
            "(手元は `show()`、web のセッションは `web_session/flows.py`)")
    return entrance_class(entrance_id)


def _has_model(annotation: Any) -> bool:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True
    return any(_has_model(argument) for argument in typing.get_args(annotation))


@cache
def _signature(cls: type[Entrypoint]) -> tuple[inspect.Signature, dict[str, TypeAdapter]]:
    """引数の signature と、型が pydantic のモデルの引数を読み込む TypeAdapter。"""
    hints = typing.get_type_hints(cls.__init__)
    return inspect.signature(cls), {name: TypeAdapter(hint) for name, hint in hints.items() if _has_model(hint)}


def call(cls: type[Entrypoint], args: dict[str, Any]) -> Any:
    """JSON で来た引数を入口の signature に当て、型が pydantic のモデルの引数はモデルに読み込んでから、入口を組み立てて
    `run()` を呼ぶ(dump 済みの結果)。引数の食い違いは ValueError にして 400 へ。"""
    signature, adapters = _signature(cls)
    try:
        signature.bind(**args)
    except TypeError as error:
        raise ValueError(f"{cls.__module__.removeprefix('data_access_logic.')}.{cls.__name__} の引数が合わない: {error}") from error
    arguments = {name: adapters[name].validate_python(value) if name in adapters else value for name, value in args.items()}
    return cls(**arguments).run()
