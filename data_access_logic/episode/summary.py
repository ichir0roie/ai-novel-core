from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.episode.models import EpisodeSourceSerialized, EpisodeSummaryDraft, PastEpisode
from db.schema import Episode, EpisodeSummary, summary_source_hash

_SYSTEM_PROMPT = """\
あなたは日本語のライトノベルの担当編集者です。
話の題と本文を一話ぶん日本語の見出しを付けた JSON で渡すので、次の話を書く作家へ渡す覚え書きを作ってください。
概要には、誰が何をして何がどうなったか、次の話へ引き継ぐ筋と、人物の立場・関係の変わりようを書いてください。
文体の覚え書きには、地の文と会話の混ぜ方・一文の長さ・視点の置き方・語り口の癖を、真似できる言い方で書いてください。
どちらも本文を写さず、四〜六文にまとめてください。"""


def summarize(s: Session, ai: AIClient, episode: Episode) -> EpisodeSummary | None:
    text = episode.text.strip()
    if not text:
        return None
    digest = summary_source_hash(text)
    row = s.scalar(select(EpisodeSummary).where(EpisodeSummary.episode_id == episode.id))
    if row is not None and row.source_hash == digest:
        return row

    prompt = "\n".join([
        EpisodeSourceSerialized.model_validate(episode).model_dump_json(indent=2),
        "この話の概要と文体を覚え書きにしてください。",
    ])
    draft = ai.generate(prompt, EpisodeSummaryDraft, system=_SYSTEM_PROMPT, timeout=constants.RECAP_TIMEOUT)
    if draft is None:
        return None
    if row is None:
        row = EpisodeSummary(story_id=episode.story_id, episode_id=episode.id)
        s.add(row)
    row.source_hash = digest
    row.summary = draft.summary
    row.style = draft.style
    s.commit()
    return row


def past_episodes(s: Session, ai: AIClient, episode: Episode, past_episode_count: int) -> list[PastEpisode]:
    query = (
        select(Episode)
        .where(
            Episode.story_id == episode.story_id,
            Episode.id != episode.id,
            Episode.text != "",
        )
        .order_by(Episode.start.desc(), Episode.id.desc())
        .limit(past_episode_count)
    )
    if episode.start is not None:
        query = query.where(Episode.start <= episode.start)
    for past in s.scalars(query).all():
        summarize(s, ai, past)
    # 要約の commit で読み込んだ関連が期限切れになるので、要約を揃えてから読み直す
    rows = s.scalars(
        query
        .join(EpisodeSummary, EpisodeSummary.episode_id == Episode.id)
        .options(selectinload(Episode.summary))
        .execution_options(populate_existing=True)
    ).all()
    return [PastEpisode.model_validate(row) for row in rows]
