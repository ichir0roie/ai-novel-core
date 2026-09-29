"""下書き(一段目)と清書(二段目)のあいだに挟む中間段。

下書きから語を洗い出してアイデアと照らし、当たったアイデアとその上位・下位を清書に渡す。
どのアイデアにも当たらなかった固有の語(`coined`)は、未確認のアイデアとして足す(候補)。
候補は確かめる(`confirmed` を 承認 にする)まで検索・清書には出ない。退けた(非承認)語は候補にも足さない。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.time_keeper import constants
from ai.time_keeper._ai import AIClient
from data_access_logic.idea.alias import called
from data_access_logic.idea.classification import find_or_create_classification
from data_access_logic.idea.models import IdeaContextMaterial, IdeaMaterial, IdeaTerm, RelatedIdeaMaterial, unique_terms
from data_access_logic.idea.search import keywords_of, search, spellings
from data_access_logic.location.models import LocationMaterial
from data_access_logic.query import common_query, dictionary_query
from db.schema import Character, ConfirmStatus, Idea, Location
from db.stamp import Stamp


def _dated(ideas: list[IdeaMaterial], time: Stamp | None) -> list[IdeaMaterial]:
    # その時刻にもうあるのかが分からないアイデアを渡すと、後の時代の設定が前の時代に紛れ込む
    if time is None:
        return ideas
    return [idea for idea in ideas if idea.start is not None]


def _candidate(s: Session, term: IdeaTerm, place_id: int | None) -> Idea | None:
    existing = s.scalar(
        select(Idea)
        .where(
            Idea.confirmed != ConfirmStatus.APPROVED,
            Idea.name.in_(spellings(term.keyword)),
        )
        .order_by(Idea.id)
    )
    if existing is not None:
        # 退けた語(非承認)は設定ではないと決めたものなので、候補に戻さず結びもしない
        return None if existing.confirmed == ConfirmStatus.REJECTED else existing

    if (s.scalar(select(Character.id).where(Character.name == term.keyword).limit(1)) is not None
            or s.scalar(select(Location.id).where(Location.name == term.keyword).limit(1)) is not None):
        return None

    classification = find_or_create_classification(s, term.kind, place_id)
    locations = ([LocationMaterial.model_validate(step) for step in common_query.place_path(s, place_id)]
                 if place_id is not None else [])
    candidate = Idea(
        name=term.keyword,
        kind=term.kind,
        confirmed=ConfirmStatus.PENDING,
        text=term.description,
        location_id=locations[0].id if locations else None,
        start=term.start,
        end=term.end,
        parent_idea_id=classification.id if classification is not None else None,
    )
    s.add(candidate)
    s.flush()
    print(f"[data_access_logic/idea] 候補を足した: {candidate.name}(id={candidate.id})")
    return candidate


def _related(s: Session, hits: list[IdeaMaterial], place_id: int | None, time: Stamp | None) -> list[IdeaMaterial]:
    related = {idea.id: idea for idea in hits}
    for idea in hits:
        parent_id = idea.parent_idea_id
        while parent_id is not None and parent_id not in related:
            parent = s.get(Idea, parent_id)
            if parent is None:
                break
            related[parent.id] = IdeaMaterial.model_validate(parent)
            parent_id = parent.parent_idea_id

    if hits:
        place_ids = common_query.idea_scope_ids(s, place_id) if place_id is not None else None
        children = s.scalars(
            dictionary_query.ideas_by_parent_select([idea.id for idea in hits], place_ids, time)
        ).all()
        for child in children:
            related.setdefault(child.id, IdeaMaterial.model_validate(child))
    return _dated(list(related.values()), time)[:constants.IDEA_CONTEXT_LIMIT]


def resolve_ideas(s: Session, keywords: list[IdeaTerm], place_id: int | None, time: Stamp | None) -> IdeaContextMaterial:
    """洗い出した語をアイデアと照らし、当たらなかった固有の語を候補として足す。

    足す候補の効く期間は語の `start` / `end`(時期のはっきりしない語は None のまま)。
    """
    terms = unique_terms(keywords)
    hits = search(s, terms, place_id, time)

    matched = {keyword for hit in hits for keyword in hit.keywords}
    candidates: dict[int, Idea] = {}
    for term in terms:
        if term.keyword in matched or not term.coined:
            continue
        candidate = _candidate(s, term, place_id)
        if candidate is not None:
            candidates.setdefault(candidate.id, candidate)

    hit_ideas = [hit.idea for hit in hits[:constants.IDEA_CONTEXT_LIMIT]]
    related = _related(s, _dated(hit_ideas, time), place_id, time)
    recognitions = called(s, [idea.id for idea in related], place_id, time)

    return IdeaContextMaterial(
        hits=hit_ideas,
        candidates=list(candidates.values()),
        related=[RelatedIdeaMaterial(idea=idea, recognition=recognitions.get(idea.id)) for idea in related],
    )


def gather_ideas(s: Session, draft: str, ai: AIClient, place_id: int | None, time: Stamp | None) -> IdeaContextMaterial:
    return resolve_ideas(s, keywords_of(draft, ai, time), place_id, time)
