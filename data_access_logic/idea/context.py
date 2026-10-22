"""下書き(一段目)と清書(二段目)のあいだに挟む中間段。

下書きから語を洗い出してアイデアと照らし、当たったアイデアとその上位を清書に渡す(下位は付けない)。
どのアイデアにも当たらなかった固有の語(`coined`)は、新しいアイデアとして足す(候補)。足した候補は、次からの検索・清書に出る。
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.idea.alias import called
from data_access_logic.idea.classification import find_or_create_classification
from data_access_logic.idea.models import IdeaContextSerialized, IdeaMaterial, IdeaDraft, RelatedIdeaMaterial, unique_ideas
from data_access_logic.idea.search import search, spellings
from data_access_logic.query import common_query
from db.schema import Character, Idea, IdeaHistory, Location
from db.stamp import Stamp

logger = logging.getLogger(__name__)


def _dated(ideas: list[IdeaMaterial], time: Stamp | None) -> list[IdeaMaterial]:
    # その時刻にもうあるのかが分からないアイデアを渡すと、後の時代の設定が前の時代に紛れ込む
    if time is None:
        return ideas
    return [idea for idea in ideas if idea.started_at(time)]


def _candidate(s: Session, idea_draft: IdeaDraft, location_id: int | None, time: Stamp | None) -> Idea | None:
    # 場所・時刻の外にあって検索に当たらなかった同じ名前のアイデアは、二重に足さずそれを結ぶ
    existing = s.scalar(select(Idea).where(Idea.name.in_(spellings(idea_draft.keyword))).order_by(Idea.id))
    if existing is not None:
        return existing

    if (s.scalar(select(Character.id).where(Character.name == idea_draft.keyword).limit(1)) is not None
            or s.scalar(select(Location.id).where(Location.name == idea_draft.keyword).limit(1)) is not None):
        return None

    classification = find_or_create_classification(s, idea_draft.kind, location_id)
    # 候補は、話の場所の属する世界線で効く。作中の人物が知るものかは分からないので、知る相手の無い行で場所と期間だけを持つ。
    # 期間は語の時期、言えなければ語の出た文の時刻から(始まりを空けると、時期未定として次から引けなくなる)
    world = common_query.location_path(s, location_id)[0] if location_id is not None else None
    candidate = Idea(
        name=idea_draft.keyword,
        kind=idea_draft.kind,
        text=idea_draft.description,
        parent_idea_id=classification.id if classification is not None else None,
        histories=[IdeaHistory(location_id=None if world is None else world.id, name=idea_draft.keyword,
                               start=idea_draft.start or time, end=idea_draft.end)],
    )
    s.add(candidate)
    s.flush()
    logger.info(f"候補を足した: {candidate.name}(id={candidate.id})")
    return candidate


def _related(s: Session, hits: list[IdeaMaterial], time: Stamp | None) -> list[IdeaMaterial]:
    """当たったアイデアと、その上位。下位は付けない(「魔物」のような分類に当たると、下位の種類がまるごと付いて膨らむ)。"""
    related = {idea.id: idea for idea in hits}
    for idea in hits:
        parent_id = idea.parent_idea_id
        while parent_id is not None and parent_id not in related:
            parent = s.get(Idea, parent_id)
            if parent is None:
                break
            related[parent.id] = IdeaMaterial.model_validate(parent)
            parent_id = parent.parent_idea_id
    return _dated(list(related.values()), time)[:constants.IDEA_CONTEXT_LIMIT]  # 足した上位にも掛ける


def resolve_ideas(
    s: Session, keywords: list[IdeaDraft], location_id: int | None, time: Stamp | None, names_only: bool = False,
) -> IdeaContextSerialized:
    """洗い出した語をアイデアと照らし、当たらなかった固有の語を候補として足す。
    `names_only` なら、名前・呼び名に当たったアイデアだけを当たりにする(`search`)。

    足す候補の効く期間は、履歴の行の語の `start` / `end`(時期のはっきりしない語は `time` から)。
    """
    idea_drafts = unique_ideas(keywords)
    hits = search(s, idea_drafts, location_id, time, names_only=names_only)

    matched = {keyword for hit in hits for keyword in hit.keywords}
    candidates: dict[int, Idea] = {}
    for idea_draft in idea_drafts:
        if idea_draft.keyword in matched or not idea_draft.coined:
            continue
        candidate = _candidate(s, idea_draft, location_id, time)
        if candidate is not None:
            candidates.setdefault(candidate.id, candidate)

    hit_ideas = [hit.idea for hit in hits[:constants.IDEA_CONTEXT_LIMIT]]
    related = _related(s, _dated(hit_ideas, time), time)
    histories = called(s, [idea.id for idea in related], location_id, time)

    return IdeaContextSerialized(
        hits=_dated(hit_ideas, time),
        candidates=list(candidates.values()),
        related=[RelatedIdeaMaterial(idea=idea, history=histories.get(idea.id)) for idea in related],
    )
