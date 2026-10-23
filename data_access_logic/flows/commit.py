#!/usr/bin/env python3
"""行を確定したあと AI の段を追いかける流れ(`CommitEvent` / `UpdateEvent` / `CommitEpisode` / `ReviseEpisode` / `CommitOracle` の `run()`)。

確定は db の段一つで済ませる(GUI の API が呼ぶ `execute(s)` と同じ)。そのあとの AI の段(ミームの抜き出し・要約・種・事実確認)は、
AI が答えなくても確定は残る。ミーム・種を抜き出すのは、その場で書いた行からだけ。
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
from data_access_logic.episode.form import EpisodeCommitForm, EpisodeReviseForm
from data_access_logic.episode.record import CommittedEpisode, EpisodeRecord
from data_access_logic.event import steps as event_steps
from data_access_logic.event.form import EventCreateForm, EventUpdateForm
from data_access_logic.event.record import EventRecord
from data_access_logic.oracle import steps as oracle_steps
from data_access_logic.oracle.form import OracleCreateForm
from data_access_logic.oracle.record import MemeSourceCommitted
from data_access_logic.source_text import SourceRow
from data_access_logic.step import RowId
from data_access_logic.flows import event_seed, fact_check, meme
from data_access_logic.caller import call
from data_access_logic.flows.summary import rewrite_event_summaries


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
    meme.refresh(ai, written)
    moved: list[CharacterMove] = []
    related: list[CharacterRelationRecord] = []
    if written:
        event_seed.refresh_and_consolidate(ai, written)
        moved = _move_cast(ai, record.id)
        related = _relate_cast(ai, record.id)
    return CommittedEpisode.model_validate({**record.model_dump(), "moves": moved, "relations": related})


def revise_episode(episode: EpisodeReviseForm, ai: AIClient = ai_client) -> EpisodeRecord:
    """`commit_episode` と違い、登場人物の居場所・関係を本文から動かさない。昔の話を推敲すると、
    今の居場所がその話の頃の場所へ戻り、とうに知り合った二人に関係が重なるので。
    推敲は筋を変えないので、種は抜き出し直さず、ミームだけを直した本文から抜き出す。"""
    record = call(episode_steps.revise_episode, episode)
    meme.refresh(ai, [SourceRow(table="episode", id=record.id)])
    return record


def commit_event(event: EventCreateForm, ai: AIClient = ai_client) -> EventRecord:
    record = call(event_steps.commit_event, event)
    written = [SourceRow(table="event", id=record.id)]
    meme.refresh(ai, written)
    rewrite_event_summaries(ai, [record.id])
    event_seed.refresh_and_consolidate(ai, written)
    return record


def update_event(event: EventUpdateForm, ai: AIClient = ai_client) -> EventRecord:
    """本文を渡したときだけ、直した本文からミームを抜き出す。"""
    record = call(event_steps.update_event, event)
    meme.refresh(ai, [SourceRow(table="event", id=record.id)] if event.text is not None else [])
    rewrite_event_summaries(ai, [record.id])
    return record


def _meme_source_follow_up(ai: AIClient, table: str, record_id: int, text: str, fact_check_enabled: bool) -> int:
    """確定したもの自身を検め、検証結果を足した本文からミームを抜き出し、足したミームも検める。足したミームの件数を返す。"""
    if fact_check_enabled and text.strip():
        fact_check.check(ai, table, ids=[record_id])
    return fact_check.extract_memes(ai, [SourceRow(table=table, id=record_id)], fact_check_enabled)


def commit_oracle(oracle: OracleCreateForm, fact_check: bool = True, ai: AIClient = ai_client) -> MemeSourceCommitted:
    committed = call(oracle_steps.commit_oracle, oracle)
    added = _meme_source_follow_up(ai, "oracle", committed.id, committed.text, fact_check)
    return MemeSourceCommitted(record=call(oracle_steps.oracle_record, RowId(id=committed.id)), memes_added=added)
