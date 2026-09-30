from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.event.models import (
    EventSerialized, EventSource, EventSourceSerialized, EventSummaryDraft, EventSummarySource,
)
from db.schema import Event, EventSummary, summary_source_hash

_SYSTEM_PROMPT = """\
あなたは日本語の小説の編集者です。
ある出来事を日本語の見出しを付けた JSON で渡すので、次の出来事を考える人へ渡す要約を作ってください。
誰が、誰に対して、何をして、どうなったかを起きた順に書き、終わっていないこと(残った問題・約束・謎)があれば最後に書いてください。
本文の文や言い回しを写さず、セリフも引かないでください。場面の分け方・締め方・文体には触れないでください。
三〜五文にまとめてください。"""


def summary_draft(ai: AIClient, event: EventSource) -> EventSummaryDraft | None:
    prompt = "\n".join([
        EventSourceSerialized.model_validate(event).model_dump_json(indent=2),
        "この出来事を要約してください。",
    ])
    return ai.generate(prompt, EventSummaryDraft, system=_SYSTEM_PROMPT, timeout=constants.EVENT_SUMMARY_TIMEOUT)


def stale_sources(s: Session, event_ids: list[int] | None) -> list[EventSummarySource]:
    """本文があるのに、要約が無いか本文と食い違っている出来事。`event_ids` を省けばすべての出来事から。"""
    query = select(Event).options(selectinload(Event.summary)).order_by(Event.id).execution_options(populate_existing=True)
    if event_ids is not None:
        query = query.where(Event.id.in_(event_ids))
    events = s.scalars(query).all()
    sources = []
    for event in events:
        text = (event.text or "").strip()
        digest = summary_source_hash(text)
        if text and (event.summary is None or event.summary.source_hash != digest):
            sources.append(EventSummarySource(
                id=event.id, name=event.name, time=event.time, start=event.start, end=event.end, text=text,
                source_hash=digest))
    return sources


def write_summary(s: Session, event_id: int, source_hash: str, text: str) -> EventSummary:
    row = s.scalar(select(EventSummary).where(EventSummary.event_id == event_id))
    if row is None:
        row = EventSummary(event_id=event_id)
        s.add(row)
    row.source_hash = source_hash
    row.text = text
    s.flush()
    return row


def summarize(s: Session, ai: AIClient, event: Event) -> EventSummary | None:
    text = (event.text or "").strip()
    if not text:
        return None
    digest = summary_source_hash(text)
    row = s.scalar(select(EventSummary).where(EventSummary.event_id == event.id))
    if row is not None and row.source_hash == digest:
        return row

    draft = summary_draft(ai, event)
    if draft is None:
        return None
    row = write_summary(s, event.id, digest, draft.text)
    s.commit()
    return row


def events_of(s: Session, query: Select[tuple[Event]]) -> list[EventSerialized]:
    """要約はそのときのまま読む(作り直さない)。"""
    events = s.scalars(
        query.options(selectinload(Event.location), selectinload(Event.summary))
        .execution_options(populate_existing=True)
    ).all()
    return [EventSerialized.model_validate(event) for event in events]


def summarized_events(s: Session, ai: AIClient, query: Select[tuple[Event]]) -> list[EventSerialized]:
    for event in s.scalars(query).all():
        summarize(s, ai, event)
    # 要約の commit で読み込んだ関連が期限切れになるので、要約を揃えてから読み直す
    return events_of(s, query)
