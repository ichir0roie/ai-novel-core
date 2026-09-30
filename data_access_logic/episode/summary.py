from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.episode.models import (
    EpisodeSourceSerialized, EpisodeSummaryDraft, PastEpisode, RecentEpisode,
)
from data_access_logic.query import common_query
from db.schema import Episode, summary_source_hash

_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの担当編集者です。
話の題と本文を一話ぶん日本語の見出しを付けた JSON で渡すので、次の話を書く作家へ渡す概要を作ってください。
概要には、誰が何をして何がどうなったか、次の話へ引き継ぐ筋と、人物の立場・関係の変わりようを書いてください。
本文を写さず、四〜六文にまとめてください。"""


def summarize(s: Session, ai: AIClient, episode: Episode) -> Episode | None:
    text = episode.main_text.strip()
    if not text:
        return None
    if episode.summary_text is not None and episode.summary_source_hash == summary_source_hash(text):
        return episode
    return rewrite_summary(s, ai, episode)


def rewrite_summary(s: Session, ai: AIClient, episode: Episode) -> Episode | None:
    text = episode.main_text.strip()
    if not text:
        return None
    prompt = "\n".join([
        EpisodeSourceSerialized.model_validate(episode).model_dump_json(indent=2),
        "この話の概要を作ってください。",
    ])
    draft = ai.generate(prompt, EpisodeSummaryDraft, system=_SYSTEM_PROMPT, timeout=constants.RECAP_TIMEOUT)
    if draft is None:
        return None
    episode.summary_source_hash = summary_source_hash(text)
    episode.summary_text = draft.summary_text
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


# 直前の話(新しい順に `constants.EPISODE_FULL_TEXT_COUNT` 話)は校正済みとみなし、文体の見本を兼ねて本文ごと渡す。古い順
def recent_episodes(s: Session, episode: Episode) -> list[RecentEpisode]:
    rows = s.scalars(_past_episodes_select(s, episode).limit(constants.EPISODE_FULL_TEXT_COUNT)).all()
    return [RecentEpisode.model_validate(row) for row in reversed(rows)]


# 新しい方から `skipped_count` 話を除いた、それより前の話すべてを概要で渡す。古い順
def summarized_episodes(s: Session, ai: AIClient, episode: Episode, skipped_count: int) -> list[PastEpisode]:
    rows = s.scalars(_past_episodes_select(s, episode).offset(skipped_count)).all()
    for past in rows:
        summarize(s, ai, past)
    return [PastEpisode.model_validate(row) for row in reversed(rows) if row.summary_text is not None]
