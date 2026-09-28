#!/usr/bin/env python3
"""下書き(一段目)と清書(二段目)のあいだに挟む中間段。

下書きから語を洗い出してアイデアと照らし、当たったアイデアとその上位・下位を清書に渡す。
どのアイデアにも当たらなかった固有の語(`coined`)は、未確認(`confirmed=未確認`)のアイデアとして足す(候補)。
候補は確かめる(`confirmed` を 承認 にする)まで検索・清書には出ない。退けた(非承認)語は候補にも足さない。下書きが踏まえたアイデアと候補は、
中間テーブル(`event_idea` など)で清書したレコードに結ぶ。
清書に渡すアイデアは本質のアイデアにそろえ、その場所・時代の作中での呼び名(`idea_alias`)で呼ばせる。
候補には `find_or_create_classification` で kind の分類(その kind をまとめる器。無ければ作る)を親として付ける。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from ai.instructions.idea_context import IDEA_CONTEXT_INSTRUCTION
from ai.time_keeper import constants, idea_alias, idea_search
from ai.time_keeper._ai import AIClient
from data_access_logic.query import common_query, dictionary_query
from db.schema import (
    ConfirmStatus,
    IDEA_LINK_MODELS, Character, Idea, Location, Session,
)
from db.stamp import Stamp


@dataclass
class IdeaContext:
    hits: list[Idea] = field(default_factory=list)
    related: list[Idea] = field(default_factory=list)
    candidates: list[Idea] = field(default_factory=list)
    # related の本質のアイデアの id ごとの、作中での呼び名
    called: dict[int, Idea] = field(default_factory=dict)

    @property
    def linked(self) -> list[Idea]:
        return list({idea.id: idea for idea in self.hits + self.candidates}.values())


def _world_id(session: Session, place_id: int | None) -> int | None:
    if place_id is None:
        return None
    path = common_query.place_path(session, place_id)
    return path[0]["id"] if path else None


def _is_proper_name(session: Session, word: str) -> bool:
    return (session.scalar(select(Character.id).where(Character.name == word).limit(1)) is not None
            or session.scalar(select(Location.id).where(Location.name == word).limit(1)) is not None)


def _location_anchor_idea(session: Session, place_id: int | None) -> Idea | None:
    """`place_id` の場所チェーン(根から)を末端から遡り、対応するアイデア(通常は「星」)が
    見つかった、一番深いものを返す。どこにも見つからなければ None。"""
    if place_id is None:
        return None
    for step in reversed(common_query.place_path(session, place_id)):
        idea = session.scalars(
            select(Idea).where(Idea.kind == step["kind"], Idea.location_id == step["id"])
            .order_by(Idea.id)).first()
        if idea is not None:
            return idea
    return None


def find_or_create_classification(session: Session, kind: str, place_id: int | None) -> Idea | None:
    """`kind` をまとめる分類のアイデア(`name == kind` の行)を、`place_id` の属する世界・星から探し、
    無ければその下に作る。分類の親は `_location_anchor_idea` が見つけたアイデア。それも見つからなければ
    親を決めようがないので None(呼び出し側は `parent_idea_id` を設定しない)。"""
    anchor = _location_anchor_idea(session, place_id)
    if anchor is None:
        return None
    existing = session.scalars(
        select(Idea).where(Idea.kind == kind, Idea.name == kind, Idea.location_id == anchor.location_id)
        .order_by(Idea.id)).first()
    if existing is not None:
        return existing
    classification = Idea(
        name=kind, kind=kind, confirmed=ConfirmStatus.APPROVED, parent_idea_id=anchor.id,
        location_id=anchor.location_id, text=f'{anchor.name}における「{kind}」のアイデアをまとめる分類。')
    session.add(classification)
    session.flush()
    print(f"[time_keepr/idea] 分類を足した: {classification.name}(id={classification.id})")
    return classification


def _candidate_for(session: Session, term: dict, place_id: int | None) -> Idea | None:
    names = idea_search.spellings(term["keyword"])
    existing = session.scalars(
        select(Idea).where(Idea.confirmed != ConfirmStatus.APPROVED, Idea.name.in_(names))
        .order_by(Idea.id)).first()
    if existing is not None:
        # 退けた語(非承認)は設定ではないと決めたものなので、候補に戻さず結びもしない
        return None if existing.confirmed == ConfirmStatus.REJECTED else existing
    if _is_proper_name(session, term["keyword"]):
        return None
    classification = find_or_create_classification(session, term["kind"], place_id)
    candidate = Idea(
        name=term["keyword"], kind=term["kind"], confirmed=ConfirmStatus.PENDING, text=term["description"],
        location_id=_world_id(session, place_id), start=term["start"], end=term["end"],
        parent_idea_id=classification.id if classification is not None else None)
    session.add(candidate)
    session.flush()
    print(f"[time_keepr/idea] 候補を足した: {candidate.name}(id={candidate.id})")
    return candidate


def _dated(ideas: list[Idea], time: Stamp | None) -> list[Idea]:
    """時刻を決めて引くときは、時期(`start`)の決まっていないアイデアを参照に入れない。
    その時刻にもうあるのかが分からないまま渡すと、後の時代の設定が前の時代に紛れ込むため。"""
    if time is None:
        return ideas
    return [idea for idea in ideas if idea.start is not None]


def _related(session: Session, hits: list[Idea], place_id: int | None, time: Stamp | None) -> list[Idea]:
    place_ids = common_query.idea_scope_ids(session, place_id) if place_id is not None else None
    related = {idea.id: idea for idea in hits}
    for idea in hits:
        parent_id = idea.parent_idea_id
        while parent_id is not None and parent_id not in related:
            parent = session.get(Idea, parent_id)
            if parent is None:
                break
            related[parent.id] = parent
            parent_id = parent.parent_idea_id
    if hits:
        for child in session.scalars(
                dictionary_query.ideas_by_parent_select([idea.id for idea in hits], place_ids, time)).all():
            related.setdefault(child.id, child)
    return _dated(list(related.values()), time)[:constants.IDEA_CONTEXT_LIMIT]


def resolve(session: Session, keywords, place_id: int | None = None, time=None) -> IdeaContext:
    """洗い出した語(`idea_search.terms_of` の形)をアイデアと照らし、当たらなかった語を候補として足す。

    `time` は出来事の時刻。その時刻に効くアイデアだけを引く。足す候補の効く期間は語の `start` / `end`
    (時期のはっきりしない語は None のまま)。
    時期の決まっていないアイデアは、語が当たっても候補は足さず、清書にも渡さない(`related` に入れない)。
    """
    time = Stamp.parse(time)
    terms = idea_search.terms_of(keywords)
    hits = idea_search.search(session, terms, place_id, time)
    matched = {keyword for hit in hits for keyword in hit.keywords}
    context = IdeaContext(hits=[hit.idea for hit in hits[:constants.IDEA_CONTEXT_LIMIT]])
    for term in terms:
        if term["keyword"] in matched or not term["coined"]:
            continue
        candidate = _candidate_for(session, term, place_id)
        if candidate is not None and candidate not in context.candidates:
            context.candidates.append(candidate)
    context.related = _dated(_related(session, _dated(context.hits, time), place_id, time), time)
    context.called = idea_alias.called(session, [idea.id for idea in context.related], place_id, time)
    return context


def gather(session: Session, draft: str, ai: AIClient, place_id: int | None = None, time=None) -> IdeaContext:
    """下書き `draft` から語を洗い出して `resolve` する。"""
    return resolve(session, idea_search.keywords_of(draft, ai, time), place_id, time)


def prompt_section(ideas: list[Idea], called: dict[int, Idea] | None = None, time=None) -> str:
    """清書のプロンプトに足す「関係する設定」の節。アイデアが無ければ空。

    `called`(`IdeaContext.called`)に呼び名があるアイデアは、その呼び名で出し、呼び名の本文を前に置く。
    `time` を渡すと、その時刻に効く追記(`IdeaNote`)まで積み重ねた本文を使う。
    """
    if not ideas:
        return ""
    called = called or {}
    lines = []
    for idea in ideas:
        text = idea_alias.text_of(idea, called, time)
        if len(text) > constants.IDEA_CONTEXT_LETTERS:
            text = text[:constants.IDEA_CONTEXT_LETTERS] + "…"
        lines.append(f"- {idea_alias.name_of(idea, called)}({idea.kind}): {text}")
    return f"関係する設定:\n{IDEA_CONTEXT_INSTRUCTION}\n" + "\n".join(lines) + "\n"


def link(session: Session, record, ideas: list[Idea]) -> int:
    """`record`(出来事・話・人物)に `ideas` を結ぶ。結んだ件数を返す(既に結んであるものは数えない)。"""
    model = IDEA_LINK_MODELS[type(record)]
    owner_column = f"{record.__tablename__}_id"
    existing = set(session.scalars(
        select(model.idea_id).where(getattr(model, owner_column) == record.id)).all())
    added = 0
    for idea in ideas:
        if idea.id in existing:
            continue
        session.add(model(**{owner_column: record.id, "idea_id": idea.id}))
        existing.add(idea.id)
        added += 1
    session.flush()
    return added


def linked_records(session: Session, idea_id: int) -> dict[str, list]:
    """アイデアを結んでいる出来事・話・人物。"""
    found = {}
    for owner, model in IDEA_LINK_MODELS.items():
        owner_column = getattr(model, f"{owner.__tablename__}_id")
        found[owner.__tablename__] = list(session.scalars(
            select(owner).join(model, owner_column == owner.id)
            .where(model.idea_id == idea_id).order_by(owner.id)).all())
    return found


def relink(session: Session, source_id: int, target_id: int | None) -> int:
    """`source_id` に結んであるものを `target_id` へ付け替える(None なら外す)。動かした件数を返す。"""
    moved = 0
    for owner, model in IDEA_LINK_MODELS.items():
        owner_column = f"{owner.__tablename__}_id"
        for row in session.scalars(select(model).where(model.idea_id == source_id)).all():
            session.delete(row)
            moved += 1
            if target_id is None:
                continue
            duplicate = session.scalar(select(model.id).where(
                getattr(model, owner_column) == getattr(row, owner_column), model.idea_id == target_id))
            if duplicate is None:
                session.add(model(**{owner_column: getattr(row, owner_column), "idea_id": target_id}))
    session.flush()
    return moved
