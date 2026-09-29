from pydantic import ValidationError
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.event.models import EventMaterial, EventSourceSerialized, EventSummaryDraft
from db.schema import Event, EventSummary, summary_source_hash

_SYSTEM_PROMPT = """\
あなたは日本語の小説の編集者です。
ある出来事を日本語の見出しを付けた JSON で渡すので、次の出来事を考える人へ渡す要約を作ってください。
誰が、誰に対して、何をして、どうなったかを起きた順に書き、終わっていないこと(残った問題・約束・謎)があれば最後に書いてください。
本文の文や言い回しを写さず、セリフも引かないでください。場面の分け方・締め方・文体には触れないでください。
三〜五文にまとめてください。"""


def summarize(s: Session, ai: AIClient, event: Event) -> EventSummary | None:
    text = (event.text or "").strip()
    if not text:
        return None
    digest = summary_source_hash(text)
    row = s.scalar(select(EventSummary).where(EventSummary.event_id == event.id))
    if row is not None and row.source_hash == digest:
        return row

    prompt = "\n".join([
        EventSourceSerialized.model_validate(event).model_dump_json(indent=2),
        "この出来事を要約してください。",
    ])
    decided = ai.try_generate_json(
        prompt, EventSummaryDraft.model_json_schema(), system=_SYSTEM_PROMPT,
        timeout=constants.EVENT_SUMMARY_TIMEOUT)
    try:
        draft = EventSummaryDraft.model_validate(decided)
    except ValidationError:
        return None
    if row is None:
        row = EventSummary(event_id=event.id)
        s.add(row)
    row.source_hash = digest
    row.text = draft.text
    s.commit()
    return row


def summarized_events(s: Session, ai: AIClient, query: Select[tuple[Event]]) -> list[EventMaterial]:
    for event in s.scalars(query).all():
        summarize(s, ai, event)
    # 要約の commit で読み込んだ関連が期限切れになるので、要約を揃えてから読み直す
    events = s.scalars(
        query.options(selectinload(Event.location), selectinload(Event.summary))
        .execution_options(populate_existing=True)
    ).all()
    return [EventMaterial.model_validate(event) for event in events]
