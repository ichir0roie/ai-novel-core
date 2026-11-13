"""話より前の話の読み出し(前後の話の時刻・人物が関わった話)。"""

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, defer, joinedload

from data_access_logic import constants
from data_access_logic.episode.models import CastAppearance, CharacterEpisodeText
from db.schema import Episode, EpisodeCharacter, Story
from db.stamp import Stamp


def _past[Q: Select](query: Q, episode: Episode) -> Q:
    """この話より前の、本文のある話に絞り、新しい順に並べる。"""
    query = query.where(Episode.id != episode.id, Episode.main_text != "")
    if episode.start is not None:
        query = query.where(Episode.start <= episode.start)
    return query.order_by(Episode.start.desc().nulls_last(), Episode.id.desc())


def _family_ids_select(episode: Episode) -> Select[int]:
    """同じ作品と、親の作品・親を同じくする作品(章・外伝)。章ごとに作品が分かれていても、
    章の頭の話に前の章の話を渡すため。親の無い作品は同じ作品だけ。"""
    parent_id = select(Story.parent_story_id).where(Story.id == episode.story_id).scalar_subquery()
    return select(Story.id).where(
        or_(Story.id == episode.story_id, Story.id == parent_id, Story.parent_story_id == parent_id))


def neighbor_starts(s: Session, episode: Episode) -> tuple[Stamp | None, Stamp | None]:
    """同じ作品(章・外伝を含む)で、この話の一つ前と一つ後の話の時刻。本文の有無は問わない(枠だけの話も話の区切り)。"""
    assert episode.start is not None
    family = select(Episode.start).where(Episode.story_id.in_(_family_ids_select(episode)), Episode.id != episode.id)
    before = s.scalar(family.where(Episode.start < episode.start).order_by(Episode.start.desc()).limit(1))
    after = s.scalar(family.where(Episode.start > episode.start).order_by(Episode.start.asc()).limit(1))
    return before, after


def latest_past_episode(s: Session, episode: Episode) -> Episode | None:
    return s.scalars(_past(select(Episode).where(Episode.story_id == episode.story_id), episode).limit(1)).first()


def recent_appearances(s: Session, episode: Episode, character_id: int) -> list[CharacterEpisodeText]:
    """人物がこの話より前に関わった話(作品を問わない)のうち、新しい `constants.EPISODE_RECENT_APPEARANCE_COUNT` 話を
    本文つきで。新しい順。プロットは読まない。"""
    links = s.scalars(
        _past(select(EpisodeCharacter).join(EpisodeCharacter.episode), episode)
        .where(EpisodeCharacter.character_id == character_id)
        .options(joinedload(EpisodeCharacter.episode).options(defer(Episode.plot_text), joinedload(Episode.story)),
                 joinedload(EpisodeCharacter.character))
        .limit(constants.EPISODE_RECENT_APPEARANCE_COUNT)
        .execution_options(populate_existing=True)
    ).all()
    return [CharacterEpisodeText.model_validate(link) for link in links]


def cast_appearances(s: Session, episode: Episode, character_ids: list[int]) -> list[CastAppearance]:
    """人物たちがこの話より前に関わった話を、話ごとにまとめて古い順に。本文は、どれかの人物の一番新しい話にだけ付ける
    (人物ごとに何話も本文で読むと、語り部の文脈が手番のたびに重くなる。古い話は題と時刻から、要れば本文を読む)。"""
    merged: dict[int, CastAppearance] = {}
    for character_id in character_ids:
        for order, link in enumerate(recent_appearances(s, episode, character_id)):
            appearance = merged.setdefault(link.episode.id, CastAppearance(episode=link.episode))
            (appearance.mentioned if link.mentioned else appearance.appeared).append(link.character)
            appearance.with_text = appearance.with_text or order == 0
    return sorted(merged.values(), key=lambda appearance: (appearance.episode.start is None, appearance.episode.start,
                                                            appearance.episode.id))
