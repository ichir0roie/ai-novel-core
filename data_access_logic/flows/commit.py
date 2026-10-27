#!/usr/bin/env python3
"""行を確定したあと AI の段を追いかける流れ(`CommitEvent` / `UpdateEvent` / `CommitEpisode` / `CommitOracle` の `run()`)。

確定は db の段一つで済ませる(GUI の API が呼ぶ `execute(s)` と同じ)。そのあとの AI の段(ミームの抜き出し・要約・種・事実確認)は、
AI が答えなくても確定は残る。種を抜き出すのは、その場で書いた行からだけ。ミームを抜き出すのは、本文を渡して確定した話の本文からだけ
(ほかの行や推敲からも抜くと、似たミームばかり増えるので)。
"""
from __future__ import annotations

from ai.claude_code import ai_client
from data_access_logic.ai_client import AIClient
from data_access_logic.character import steps as character_steps
from data_access_logic.character.moves import allowed_moves
from data_access_logic.character.record import CharacterMove, CharacterRelationRecord
from data_access_logic.episode import moves as episode_moves
from data_access_logic.episode.relations import RelationsForm, allowed_relations, relations_draft
from data_access_logic.episode import steps as episode_steps
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.episode.record import CommittedEpisode
from data_access_logic.event import steps as event_steps
from data_access_logic.event.form import EventCreateForm, EventUpdateForm
from data_access_logic.event.record import EventRecord
from data_access_logic.oracle import steps as oracle_steps
from data_access_logic.oracle.form import OracleCreateForm
from data_access_logic.oracle.record import OracleRecord
from data_access_logic.source_text import SourceRow
from data_access_logic.step import RowId
from data_access_logic.flows import event_seed, meme
from data_access_logic.flows.fact_check import check
from data_access_logic.caller import call
from data_access_logic.flows.summary import rewrite_event_summaries
from db.writer import generated


def _move_cast(ai: AIClient, episode_id: int) -> list[CharacterMove]:
    """本文の中で住まい・拠点が変わった登場人物の移動先を AI に返させ、登場人物と移動先の候補に当たるものだけで居場所を移す。"""
    material = call(episode_steps.moves_material, RowId(id=episode_id))
    if material is None:
        return []
    moves = allowed_moves(episode_moves.moves_draft(ai, material), [member.id for member in material.cast],
                          [destination.id for destination in material.destinations])
    if not moves:
        return []
    return call(character_steps.move_characters, character_steps.MovesForm(moves=moves, time=material.time))


def _relate_cast(ai: AIClient, episode_id: int) -> list[CharacterRelationRecord]:
    """本文で会った・知り合いだと分かった登場人物どうしの関係を AI に返させ、まだ関係の無い向きだけを話の時刻から足す。"""
    material = call(episode_steps.relations_material, RowId(id=episode_id))
    if material is None:
        return []
    drafts = allowed_relations(relations_draft(ai, material),
                               [member.id for member in material.cast], material.relations)
    if not drafts:
        return []
    return call(episode_steps.add_relations, RelationsForm(relations=drafts, time=material.time))


def commit_episode(episode: EpisodeCommitForm, ai: AIClient = ai_client) -> CommittedEpisode:
    """本文を渡したときは、その本文からミームと出来事の種を抜き出す。本文の中で住まい・拠点が変わった登場人物の居場所も移し、
    その移動先をレスポンスの `moves` に返す(移動先が空なら何もしない)。本文で会った・知り合いだと分かった登場人物どうしの関係も足し、
    レスポンスの `relations` に返す。"""
    record = call(episode_steps.commit_episode, episode)
    written = [SourceRow(table="episode", id=record.id)] if episode.main_text is not None else []
    moved: list[CharacterMove] = []
    related: list[CharacterRelationRecord] = []
    with generated():
        if written:
            meme.refresh(ai, written)
            event_seed.refresh_and_consolidate(ai, written)
            moved = _move_cast(ai, record.id)
            related = _relate_cast(ai, record.id)
    return CommittedEpisode.model_validate({**record.model_dump(), "moves": moved, "relations": related})


def commit_event(event: EventCreateForm, ai: AIClient = ai_client) -> EventRecord:
    record = call(event_steps.commit_event, event)
    written = [SourceRow(table="event", id=record.id)]
    with generated():
        rewrite_event_summaries(ai, [record.id])
        event_seed.refresh_and_consolidate(ai, written)
    return record


def update_event(event: EventUpdateForm, ai: AIClient = ai_client) -> EventRecord:
    record = call(event_steps.update_event, event)
    with generated():
        rewrite_event_summaries(ai, [record.id])
    return record


def commit_oracle(oracle: OracleCreateForm, fact_check: bool = True, ai: AIClient = ai_client) -> OracleRecord:
    committed = call(oracle_steps.commit_oracle, oracle)
    if fact_check and committed.text.strip():
        with generated():
            check(ai, "oracle", ids=[committed.id])
    return call(oracle_steps.oracle_record, RowId(id=committed.id))
