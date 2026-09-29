from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.time_keeper import constants, idea_alias, idea_search
from ai.time_keeper._ai import AIClient
from ai.time_keeper.idea_context import find_or_create_classification
from data_access_logic.idea.models import IdeaContextMaterial
from data_access_logic.query import common_query, dictionary_query
from db.schema import Character, ConfirmStatus, Idea, Location
from db.stamp import Stamp


def _dated(ideas: list[Idea], time: Stamp | None) -> list[Idea]:
    # その時刻にもうあるのかが分からないアイデアを渡すと、後の時代の設定が前の時代に紛れ込む
    if time is None:
        return ideas
    return [idea for idea in ideas if idea.start is not None]


def _candidate(s: Session, term: dict, place_id: int | None) -> Idea | None:
    existing = s.scalar(
        select(Idea)
        .where(
            Idea.confirmed != ConfirmStatus.APPROVED,
            Idea.name.in_(idea_search.spellings(term["keyword"])),
        )
        .order_by(Idea.id)
    )
    if existing is not None:
        # 退けた語(非承認)は設定ではないと決めたものなので、候補に戻さず結びもしない
        return None if existing.confirmed == ConfirmStatus.REJECTED else existing

    keyword = term["keyword"]
    if (s.scalar(select(Character.id).where(Character.name == keyword).limit(1)) is not None
            or s.scalar(select(Location.id).where(Location.name == keyword).limit(1)) is not None):
        return None

    classification = find_or_create_classification(s, term["kind"], place_id)
    path = common_query.place_path(s, place_id) if place_id is not None else []
    candidate = Idea(
        name=keyword,
        kind=term["kind"],
        confirmed=ConfirmStatus.PENDING,
        text=term["description"],
        location_id=path[0]["id"] if path else None,
        start=term["start"],
        end=term["end"],
        parent_idea_id=classification.id if classification is not None else None,
    )
    s.add(candidate)
    s.flush()
    print(f"[data_access_logic/idea] 候補を足した: {candidate.name}(id={candidate.id})")
    return candidate


def _related(s: Session, hits: list[Idea], place_id: int | None, time: Stamp | None) -> list[Idea]:
    related = {idea.id: idea for idea in hits}
    for idea in hits:
        parent_id = idea.parent_idea_id
        while parent_id is not None and parent_id not in related:
            parent = s.get(Idea, parent_id)
            if parent is None:
                break
            related[parent.id] = parent
            parent_id = parent.parent_idea_id

    if hits:
        place_ids = common_query.idea_scope_ids(s, place_id) if place_id is not None else None
        children = s.scalars(
            dictionary_query.ideas_by_parent_select([idea.id for idea in hits], place_ids, time)
        ).all()
        for child in children:
            related.setdefault(child.id, child)
    return _dated(list(related.values()), time)[:constants.IDEA_CONTEXT_LIMIT]


def gather_ideas(
    s: Session,
    draft: str,
    ai: AIClient,
    place_id: int | None,
    time: Stamp | None,
) -> IdeaContextMaterial:
    terms = idea_search.keywords_of(draft, ai, time)
    hits = idea_search.search(s, terms, place_id, time)

    matched = {keyword for hit in hits for keyword in hit.keywords}
    candidates: dict[int, Idea] = {}
    for term in terms:
        if term["keyword"] in matched or not term["coined"]:
            continue
        candidate = _candidate(s, term, place_id)
        if candidate is not None:
            candidates.setdefault(candidate.id, candidate)

    hit_ideas = [hit.idea for hit in hits[:constants.IDEA_CONTEXT_LIMIT]]
    related = _related(s, _dated(hit_ideas, time), place_id, time)
    recognitions = idea_alias.called(s, [idea.id for idea in related], place_id, time)

    return IdeaContextMaterial(
        hits=hit_ideas,
        candidates=list(candidates.values()),
        related=related,
        recognitions=list(recognitions.values()),
    )
