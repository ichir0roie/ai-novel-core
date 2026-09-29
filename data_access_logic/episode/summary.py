from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.episode.models import (
    EpisodeSourceSerialized, EpisodeSummaryDraft, PastEpisode, RecentEpisode,
)
from data_access_logic.query import common_query
from db.schema import Episode, EpisodeSummary, summary_source_hash

_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの担当編集者です。
話の題と本文を一話ぶん日本語の見出しを付けた JSON で渡すので、次の話を書く作家へ渡す概要を作ってください。
概要には、誰が何をして何がどうなったか、次の話へ引き継ぐ筋と、人物の立場・関係の変わりようを書いてください。
本文を写さず、四〜六文にまとめてください。"""


def summarize(s: Session, ai: AIClient, episode: Episode) -> EpisodeSummary | None:
    text = episode.text.strip()
    if not text:
        return None
    row = s.scalar(select(EpisodeSummary).where(EpisodeSummary.episode_id == episode.id))
    if row is not None and row.source_hash == summary_source_hash(text):
        return row
    return rewrite_summary(s, ai, episode)


def rewrite_summary(s: Session, ai: AIClient, episode: Episode) -> EpisodeSummary | None:
    text = episode.text.strip()
    if not text:
        return None
    prompt = "\n".join([
        EpisodeSourceSerialized.model_validate(episode).model_dump_json(indent=2),
        "この話の概要を作ってください。",
    ])
    draft = ai.generate(prompt, EpisodeSummaryDraft, system=_SYSTEM_PROMPT, timeout=constants.RECAP_TIMEOUT)
    if draft is None:
        return None
    row = s.scalar(select(EpisodeSummary).where(EpisodeSummary.episode_id == episode.id))
    if row is None:
        row = EpisodeSummary(story_id=episode.story_id, episode_id=episode.id)
        s.add(row)
    row.source_hash = summary_source_hash(text)
    row.summary = draft.summary
    s.commit()
    return row


# 章・外伝に分けた作品でも筋を切らないよう、一番上の作品とその子孫の話をまとめて時刻の順に見る
def _past_episodes_select(s: Session, episode: Episode) -> Select[tuple[Episode]]:
    query = (
        select(Episode)
        .where(
            Episode.story_id.in_(common_query.story_family_ids(s, episode.story_id)),
            Episode.id != episode.id,
            Episode.text != "",
        )
        .order_by(Episode.start.desc(), Episode.id.desc())
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
    query = _past_episodes_select(s, episode).offset(skipped_count)
    for past in s.scalars(query).all():
        summarize(s, ai, past)
    # 要約の commit で読み込んだ関連が期限切れになるので、要約を揃えてから読み直す
    rows = s.scalars(
        query
        .join(EpisodeSummary, EpisodeSummary.episode_id == Episode.id)
        .options(selectinload(Episode.summary))
        .execution_options(populate_existing=True)
    ).all()
    return [PastEpisode.model_validate(row) for row in reversed(rows)]
