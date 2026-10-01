from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, joinedload

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.episode.models import (
    CharacterEpisode, EpisodeSource, EpisodeSourceSerialized, EpisodeSummaryDraft, EpisodeSummarySource, PastEpisode,
    RecentEpisode,
)
from db.schema import Character, Episode, EpisodeCharacter, summary_source_hash

_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの担当編集者です。
話の題と本文を一話ぶん日本語の見出しを付けた JSON で渡すので、次の話を書く作家へ渡す概要を作ってください。
概要には、誰が何をして何がどうなったか、次の話へ引き継ぐ筋と、人物の立場・関係の変わりようを書いてください。
本文を写さず、四〜六文にまとめてください。"""


def summary_draft(ai: AIClient, episode: EpisodeSource) -> EpisodeSummaryDraft | None:
    prompt = "\n".join([
        EpisodeSourceSerialized.model_validate(episode).model_dump_json(indent=2),
        "この話の概要を作ってください。",
    ])
    return ai.generate(prompt, EpisodeSummaryDraft, system=_SYSTEM_PROMPT, timeout=constants.RECAP_TIMEOUT)


def _stale(episode: Episode) -> bool:
    text = episode.main_text.strip()
    return bool(text) and (episode.summary_text is None or episode.summary_source_hash != summary_source_hash(text))


def summary_sources(s: Session, episode_ids: list[int] | None, stale_only: bool) -> list[EpisodeSummarySource]:
    """本文のある話。`stale_only` なら、概要が無いか本文と食い違っている話だけ。`episode_ids` を省けばすべての話から。"""
    query = select(Episode).order_by(Episode.id)
    if episode_ids is not None:
        query = query.where(Episode.id.in_(episode_ids))
    episodes = s.scalars(query).all()
    return [
        EpisodeSummarySource(id=episode.id, title=episode.title, main_text=episode.main_text,
                             source_hash=summary_source_hash(episode.main_text.strip()))
        for episode in episodes
        if episode.main_text.strip() and (_stale(episode) or not stale_only)
    ]


def write_summary(s: Session, episode_id: int, source_hash: str, summary_text: str) -> Episode:
    episode = s.get_one(Episode, episode_id)
    episode.summary_source_hash = source_hash
    episode.summary_text = summary_text
    s.flush()
    return episode


def summarize(s: Session, ai: AIClient, episode: Episode) -> Episode | None:
    if not episode.main_text.strip():
        return None
    if not _stale(episode):
        return episode
    return rewrite_summary(s, ai, episode)


def rewrite_summary(s: Session, ai: AIClient, episode: Episode) -> Episode | None:
    text = episode.main_text.strip()
    if not text:
        return None
    draft = summary_draft(ai, episode)
    if draft is None:
        return None
    write_summary(s, episode.id, summary_source_hash(text), draft.summary_text)
    s.commit()
    return episode


def _before[Q: Select](query: Q, episode: Episode) -> Q:
    """この話より前の、本文のある話に絞る。"""
    query = query.where(Episode.id != episode.id, Episode.main_text != "")
    if episode.start is not None:
        query = query.where(Episode.start <= episode.start)
    return query


def _past(query: Select[Episode], episode: Episode) -> Select[Episode]:
    """新しい順。"""
    return _before(query, episode).order_by(Episode.start.desc().nulls_last(), Episode.id.desc())


def _story_past_select(episode: Episode) -> Select[Episode]:
    return _past(select(Episode).where(Episode.story_id == episode.story_id), episode)


def _related_ids_select(characters: list[Character]) -> Select[int]:
    """人物が登場するか名前が出る話(作品を問わない)。"""
    return select(EpisodeCharacter.episode_id).where(
        EpisodeCharacter.character_id.in_([character.id for character in characters]))


def latest_past_episode(s: Session, episode: Episode) -> Episode | None:
    return s.scalars(_story_past_select(episode).limit(1)).first()


def _recent_rows(s: Session, episode: Episode, full_text_count: int) -> list[Episode]:
    return list(s.scalars(_story_past_select(episode).limit(full_text_count)).all())


# 同じ作品の直前の話(新しい順に `constants.EPISODE_FULL_TEXT_COUNT` 話)は校正済みとみなし、文体の見本を兼ねて本文ごと渡す。古い順
def recent_episodes(s: Session, episode: Episode) -> list[RecentEpisode]:
    rows = _recent_rows(s, episode, constants.EPISODE_FULL_TEXT_COUNT)
    return [RecentEpisode.model_validate(row) for row in reversed(rows)]


def _summarized_select(s: Session, episode: Episode, characters: list[Character], full_text_count: int) -> Select[Episode]:
    """同じ作品のすべての話と、登場人物が関わるすべての話(重ならない)。本文で渡す直前の `full_text_count` 話は除く。"""
    recent_ids = [row.id for row in _recent_rows(s, episode, full_text_count)]
    return _past(
        select(Episode).where(
            or_(Episode.story_id == episode.story_id, Episode.id.in_(_related_ids_select(characters))),
            Episode.id.not_in(recent_ids)),
        episode)


def past_episode_ids(s: Session, episode: Episode, characters: list[Character], full_text_count: int) -> list[int]:
    """`past_episodes` が概要で渡す話(概要を揃えておく話)。"""
    return list(s.scalars(
        _summarized_select(s, episode, characters, full_text_count).with_only_columns(Episode.id)).all())


# 古い順。概要はそのときのまま読む(作り直さない)
def past_episodes(s: Session, episode: Episode, characters: list[Character], full_text_count: int) -> list[PastEpisode]:
    rows = s.scalars(
        _summarized_select(s, episode, characters, full_text_count).options(joinedload(Episode.story))
        .execution_options(populate_existing=True)).all()
    return [PastEpisode.model_validate(row) for row in reversed(rows) if row.summary_text is not None]


def appearances(s: Session, episode: Episode, characters: list[Character]) -> list[CharacterEpisode]:
    """人物ごとの、この話より前に関わった話(作品を問わない)。古い順。"""
    links = s.scalars(
        _before(select(EpisodeCharacter).join(EpisodeCharacter.episode), episode)
        .where(EpisodeCharacter.character_id.in_([character.id for character in characters]))
        .options(joinedload(EpisodeCharacter.episode).joinedload(Episode.story))
        .order_by(Episode.start.nulls_last(), Episode.id)
        .execution_options(populate_existing=True)
    ).all()
    return [CharacterEpisode.model_validate(link) for link in links]
