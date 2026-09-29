#!/usr/bin/env python3
"""`local_ai` には本文を書く生成器が無いので、ここだけは claude_ai 固有。
自動生成なので `synced` は立てて確定する(`schema.py` の `Episode.synced` の注記どおり)。
"""
from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ai.instructions import style
from ai.claude_code import ai_client
from ai.instructions.idea_context import IDEA_CONTEXT_INSTRUCTION
from ai.time_keeper import idea_context
from data_access_logic.idea.context import gather_ideas
from data_access_logic.query import common_query
from data_access_logic.episode.models import EpisodeDraft, EpisodeMaterial, EpisodeMaterialSerialized
from db.schema import *


# 一話ぶんの本文を書かせるので、断片の JSON より長く待つ。
EPISODE_TIMEOUT = 900.0

# 本文の代わりに要約で渡す、直前の話の本数。
RECAP_EPISODE_LIMIT = 3


def _system_prompt(*, shared_style_extra: str = "", style_extra: str = "") -> str:
    return f"""\
あなたは日本語のライトノベルを書く作家です。
作品・直前の話・書く話(時刻・場所・視点・登場人物・種)を日本語の見出しを付けた JSON で渡すので、この作品の次の話を一話ぶん書いてください。
直前の話は本文の代わりに概要で渡します。概要の筋をそのまま受け継ぎ、揃える文体を渡したときはそれに揃えてください。
{style.style_instruction("episode", shared_extra=shared_style_extra, extra=style_extra)}
種を渡したときは、それを場面まで展開したものを本文にしてください。種に無い出来事を足さないでください。
{IDEA_CONTEXT_INSTRUCTION}
JSON で答えてください。キーは title(サブタイトル。短く)と text(本文)の二つだけ。"""


# 文体の好み(舞台設定・既存の話から抽出した文体の癖など)を渡さない既定の文面。
_SYSTEM_PROMPT = _system_prompt()


def _episode_materials(
    s: Session,
    episode_id: int,
    past_episode_count: int
) -> EpisodeMaterial:
    episode = s.scalar(
        select(Episode)
        .where(
            Episode.id == episode_id
        )
        .options(
            joinedload(Episode.place),
            joinedload(Episode.viewpoint_character),
            selectinload(Episode.episode_characters).joinedload(EpisodeCharacter.character),
        )
        .execution_options(populate_existing=True)
    )

    if episode is None:
        raise ValueError()

    story = s.get(Story, episode.story_id)
    if story is None:
        raise ValueError()

    locations = common_query.place_path(s, episode.place_id) if episode.place_id else []

    past_episodes = s.scalars(
        select(Episode)
        .join(EpisodeSummary, EpisodeSummary.episode_id == Episode.id)
        .where(
            Episode.story_id == story.id,
            Episode.id != episode.id,
            Episode.start <= episode.start,
        )
        .options(
            selectinload(Episode.summary),
        )
        .execution_options(populate_existing=True)
        .order_by(Episode.start.desc())
        .limit(past_episode_count)
    ).all()

    ideas = gather_ideas(s, episode.key, ai_client, episode.place_id, episode.start)

    return EpisodeMaterial(
        story=story,
        main_episode=episode,
        past_episodes=past_episodes,
        locations=locations,
        ideas=ideas,
    )


def write_next_episode(
    session: Session,
    episode_id: int,
    past_episode_count: int = RECAP_EPISODE_LIMIT,
    shared_style_extra: str = "", style_extra: str = "",
) -> Episode | None:
    material = _episode_materials(session, episode_id, past_episode_count)

    prompt = "\n".join([
        EpisodeMaterialSerialized.model_validate(material).model_dump_json(indent=2),
        "この作品の次の話を書いてください。",
    ])
    system_prompt = (_system_prompt(shared_style_extra=shared_style_extra, style_extra=style_extra)
                     if (shared_style_extra or style_extra) else _SYSTEM_PROMPT)
    decided = ai_client.try_generate_json(
        prompt, EpisodeDraft.model_json_schema(), system=system_prompt, timeout=EPISODE_TIMEOUT,
        model=ai_client.EPISODE_MODEL, effort=ai_client.EPISODE_EFFORT)
    try:
        draft = EpisodeDraft.model_validate(decided)
    except ValidationError as error:
        print(f"[claude_ai/story] {material.story.name}: 本文が得られなかったので見送り: {error}")
        return None

    record = session.get_one(Episode, episode_id)
    record.title = draft.title or record.title
    record.synced = True
    record.text = draft.text
    session.flush()
    idea_context.link(session, record, material.ideas.linked)
    session.commit()
    print(f"[claude_ai/story] {material.story.name}「{record.title}」"
          f" id={record.id} {record.letters}字")
    return record
