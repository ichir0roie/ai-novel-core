"""話の本文の要約(`episode_summary`)。居合わせた人物役が、前の話を覚えている形で読む。

話のあとの差分の来歴は、本人が変わったこと(境遇・持ち物・知った秘密)だけにし、話の中でしたことの流れはこの要約で受け継ぐ。
要約は場面ごとに、その場に居合わせた人物と、起きたこと・交わした言葉を書く。人物役は、自分のいた場面だけを覚えている
ものとして読む。胸の内は書かない(人物役に、ほかの人物の内心が漏れないように)。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from data_access_logic.ai_client import AIClient
from data_access_logic.event.models import EventSummaryDraft
from data_access_logic.material import Material, Timestamp
from db.schema import Episode, EpisodeSummary, StyleScope, summary_source_hash

_SYSTEM = """\
話の本文を渡すので、この話に居合わせた人物が後で思い出すための要約を作る。
場面ごとに一段落にし、段落の頭に「場所・居合わせた人物:」を書いてから、誰が誰に何をして、何を言い、どうなったかを起きた順に書く。
交わした約束・頼みごと・知らされたこと・残った問題は落とさない。人物の胸の内・考えたことは書かず、見えたこと・聞こえたことだけを書く。
要約はそのまま人物に渡るので、年・日付・時刻(暦の時刻)を書かない。時の移りは「朝」「昼すぎ」「夜ふけ」「前の日」のような言い方で書く。
一場面二〜四文。"""


class EpisodeSummarySource(Material):
    id: int
    title: str
    start: Timestamp | None = None
    main_text: str
    source_hash: str

    def for_prompt(self) -> str:
        # 時刻は渡さない(要約に年・日付を書き写させない)
        return f"題: {self.title}\n本文:\n{self.main_text}"


def summary_draft(ai: AIClient, source: EpisodeSummarySource) -> EventSummaryDraft | None:
    prompt = "\n".join([source.for_prompt(), "この話を要約する。"])
    return ai.generate(prompt, EventSummaryDraft, system=_SYSTEM, style_scope=StyleScope.EVENT)


def stale_sources(s: Session, episode_ids: list[int] | None) -> list[EpisodeSummarySource]:
    """本文があるのに、要約が無いか本文と食い違っている話。`episode_ids` を省けばすべての話から。"""
    query = (select(Episode).options(selectinload(Episode.summary)).order_by(Episode.id)
             .execution_options(populate_existing=True))
    if episode_ids is not None:
        query = query.where(Episode.id.in_(episode_ids))
    sources = []
    for episode in s.scalars(query).all():
        text = (episode.main_text or "").strip()
        digest = summary_source_hash(text)
        if text and (episode.summary is None or episode.summary.source_hash != digest):
            sources.append(EpisodeSummarySource(id=episode.id, title=episode.title or "", start=episode.start,
                                                main_text=text, source_hash=digest))
    return sources


def write_summary(s: Session, episode_id: int, source_hash: str, text: str) -> EpisodeSummary:
    row = s.scalar(select(EpisodeSummary).where(EpisodeSummary.episode_id == episode_id))
    if row is None:
        row = EpisodeSummary(episode_id=episode_id)
        s.add(row)
    row.source_hash = source_hash
    row.text = text
    s.flush()
    return row
