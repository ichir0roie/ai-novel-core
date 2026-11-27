"""人物が居合わせた前の話(人物役が「居合わせた話」として要約で覚えている話)。"""
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from data_access_logic import constants
from data_access_logic.episode.mentions import cast_characters
from data_access_logic.episode.material import load_episode
from db.schema import Episode, EpisodeCharacter
from db.stamp import Stamp


def past_episodes_select(character_id: int, time: Stamp, acting_episode_id: int | None) -> Select[Episode]:
    """`time` より前に始まった、本文のある、人物が登場人物の話(名前だけ出る話は除く)を新しい順に
    `constants.KNOWLEDGE_EPISODE_LIMIT` 件。演じている話は除く。"""
    query = (select(Episode).join(EpisodeCharacter, EpisodeCharacter.episode_id == Episode.id)
             .where(EpisodeCharacter.character_id == character_id, EpisodeCharacter.mentioned.is_(False),
                    Episode.start < time, Episode.main_text != ""))
    if acting_episode_id is not None:
        query = query.where(Episode.id != acting_episode_id)
    return query.order_by(Episode.start.desc(), Episode.id.desc()).limit(constants.KNOWLEDGE_EPISODE_LIMIT)


def cast_past_episode_ids(s: Session, episode_id: int) -> list[int]:
    episode = load_episode(s, episode_id)
    if episode.start is None:
        return []
    ids = [row.id for character in cast_characters(episode)
           for row in s.scalars(past_episodes_select(character.id, episode.start, episode.id)).all()]
    return list(dict.fromkeys(ids))
