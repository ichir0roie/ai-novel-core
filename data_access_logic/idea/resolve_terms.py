#!/usr/bin/env python3
"""洗い出した語をアイデアと照らす、claude が呼ぶ入口(中間段を claude が自分で回すとき)。

    ResolveTerms([IdeaTerm(keyword="虫憑き", variants=["寄生", "宿り"], description="…", kind="呼称",
                           start="1190")],
                 place_id=61, time="1200/04/01").show()

`time` は出来事の時刻。その時刻に効くアイデアだけを引く。
当たったアイデアとその上位・下位を `ideas` に返す。作中の呼び名(`idea_recognition`)に当たっても本質の
アイデアにそろえ、その場所・時刻での呼び名を `called` に付ける。どれにも当たらなかった語は、`kind` の種別で
未確認(`confirmed=未確認`)のアイデアとして足し、`candidates` に返す。足した候補は語の `start` から `end` まで効く。
`start` は `time` と下書きの中身からある程度はっきり言えるときだけ付け、言えなければ省く(None)。`end` は分かるときだけ付ける。
清書したら `idea.link_ideas.LinkIdeas` で、`hits` と `candidates` の id を清書したレコードに結ぶ。
"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.idea.context import resolve_ideas
from data_access_logic.idea.models import IdeaMaterial, IdeaRecognitionMaterial, IdeaTerm
from db.schema import ConfirmStatus, Idea
from db.stamp import Stamp


class ResolvedIdea(BaseModel):
    id: int
    name: str
    kind: str
    confirmed: ConfirmStatus
    parent_idea_id: int | None = None
    called: str
    text: str | None = None


class ResolvedTerms(BaseModel):
    ideas: list[ResolvedIdea]
    hits: list[int]
    candidates: list[ResolvedIdea]


def _resolved(idea: IdeaMaterial, recognition: IdeaRecognitionMaterial | None = None) -> ResolvedIdea:
    return ResolvedIdea(id=idea.id, name=idea.name, kind=idea.kind, confirmed=idea.confirmed,
                        parent_idea_id=idea.parent_idea_id,
                        called=recognition.name if recognition else idea.name, text=idea.text)


class ResolveTerms(CommitEntrypoint):
    model = Idea

    def __init__(self, terms: list[IdeaTerm], place_id: int | None = None, time: Stamp | str | None = None):
        self.terms = terms
        self.place_id = place_id
        self.time = Stamp.parse(time)

    def execute(self, session: Session) -> ResolvedTerms:
        context = resolve_ideas(session, self.terms, self.place_id, self.time)
        return ResolvedTerms(ideas=[_resolved(related.idea, related.recognition) for related in context.related],
                             hits=[idea.id for idea in context.hits],
                             candidates=[_resolved(idea) for idea in context.candidates])
