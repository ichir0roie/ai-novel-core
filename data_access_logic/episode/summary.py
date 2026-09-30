from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.episode.models import (
    EpisodeSource, EpisodeSourceSerialized, EpisodeSummaryDraft, EpisodeSummarySource, PastEpisode, RecentEpisode,
)
from data_access_logic.query import common_query
from db.schema import Episode, summary_source_hash

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


# 章・外伝に分けた作品でも筋を切らないよう、一番上の作品とその子孫の話をまとめて時刻の順に見る
def _past_episodes_select(s: Session, episode: Episode) -> Select[Episode]:
    query = (
        select(Episode)
        .where(
            Episode.story_id.in_(common_query.story_family_ids(s, episode.story_id)),
            Episode.id != episode.id,
            Episode.main_text != "",
        )
        .order_by(Episode.start.desc().nulls_last(), Episode.id.desc())
    )
    if episode.start is not None:
        query = query.where(Episode.start <= episode.start)
    return query


def latest_past_episode(s: Session, episode: Episode) -> Episode | None:
    return s.scalars(_past_episodes_select(s, episode).limit(1)).first()


# 直前の話(新しい順に `constants.EPISODE_FULL_TEXT_COUNT` 話)は校正済みとみなし、文体の見本を兼ねて本文ごと渡す。古い順
def recent_episodes(s: Session, episode: Episode) -> list[RecentEpisode]:
    rows = s.scalars(_past_episodes_select(s, episode).limit(constants.EPISODE_FULL_TEXT_COUNT)).all()
    return [RecentEpisode.model_validate(row) for row in reversed(rows)]


def past_episode_ids(s: Session, episode: Episode, skipped_count: int) -> list[int]:
    """`summarized_episodes` が概要で渡す話(概要を揃えておく話)。"""
    return list(s.scalars(_past_episodes_select(s, episode).offset(skipped_count).with_only_columns(Episode.id)).all())


# 新しい方から `skipped_count` 話を除いた、それより前の話すべてを概要で渡す。古い順。概要はそのときのまま読む(作り直さない)
def past_episodes(s: Session, episode: Episode, skipped_count: int) -> list[PastEpisode]:
    rows = s.scalars(_past_episodes_select(s, episode).offset(skipped_count)).all()
    return [PastEpisode.model_validate(row) for row in reversed(rows) if row.summary_text is not None]


def summarized_episodes(s: Session, ai: AIClient, episode: Episode, skipped_count: int) -> list[PastEpisode]:
    for past in s.scalars(_past_episodes_select(s, episode).offset(skipped_count)).all():
        summarize(s, ai, past)
    return past_episodes(s, episode, skipped_count)
