#!/usr/bin/env python3
"""入口の id から、それに当たる web の流れを引いて回す(web のセッションの Claude が入口を呼ぶ口)。

claude を叩く入口(`gui/api/interface.py` の `claude` が立つもの)は、どれもここに流れを持つ。
db だけの入口は、API の入口(`/api/interface/{id}`)をそのまま呼ぶ。
"""
from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from typing import Any

from pydantic import TypeAdapter

from gui.api import interface
from web_session import character, commit, episode, event, refresh
from web_session.api import run_entrance

REFRESH = "meme.refresh_generated_content.RefreshGeneratedContent"

FLOWS: dict[str, Callable[..., Any]] = {
    "character.generate_character.GenerateCharacter": character.generate_character,
    "character.generate_characters.GenerateCharacters": character.generate_characters,
    "episode.commit_episode.CommitEpisode": commit.commit_episode,
    "episode.complete_plot.CompletePlot": episode.complete_plot,
    "episode.generate_frame.GenerateFrame": episode.generate_frame,
    "episode.read_episode_brief.ReadEpisodeBrief": episode.read_episode_brief,
    "episode.read_episode_casting.ReadEpisodeCasting": episode.read_episode_casting,
    "episode.rewrite_episode_summary.RewriteEpisodeSummary": episode.rewrite_episode_summary,
    "event.commit_event.CommitEvent": commit.commit_event,
    "event.generate_event.GenerateEvent": event.generate_event,
    "event.update_event.UpdateEvent": commit.update_event,
    "fact_check.check_facts.CheckFacts": refresh.check_facts,
    "idea.commit_idea.CommitIdea": commit.commit_idea,
    "meme.extract_memes.ExtractMemes": refresh.extract_memes,
    REFRESH: refresh.refresh_generated_content,
    "oracle.commit_oracle.CommitOracle": commit.commit_oracle,
    "story.commit_story.CommitStory": commit.commit_story,
}


def run(entrance_id: str, args: dict[str, Any]) -> Any:
    """引数を流れの型注釈のモデルに読み、結果を JSON にして返す。"""
    flow = FLOWS.get(entrance_id)
    if flow is None:
        if interface.entrance_of(entrance_id).claude:
            raise ValueError(f"{entrance_id} は claude を叩くのに、web の流れ(web_session/flows.py)が無い")
        return run_entrance(entrance_id, args)
    hints = typing.get_type_hints(flow)
    try:
        bound = inspect.signature(flow).bind(**args)
    except TypeError as error:
        raise ValueError(f"{entrance_id} の引数が合わない: {error}") from error
    arguments = {name: TypeAdapter(hints[name]).validate_python(value) for name, value in bound.arguments.items()}
    return TypeAdapter(hints["return"]).dump_python(flow(**arguments), mode="json")
