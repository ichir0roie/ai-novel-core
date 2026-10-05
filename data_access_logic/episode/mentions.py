#!/usr/bin/env python3
"""話に名前だけ出る人物(`episode_character.mentioned`)を、プロット・本文から拾い直す。

登場人物(`mentioned` でない行)は作者が決めるので触らない。拾うのは、人物・対象のうち、
登場人物でなく、名前がプロット・本文に語として出るもの。ただし話の時刻に別の星に住んでいる人物は、
同じ名の別人(地球のテオと港町のテオなど)なので拾わない。
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from data_access_logic.material import Named
from data_access_logic.query import common_query
from db.schema import Character, Episode, EpisodeCharacter
from db.stamp import Stamp

logger = logging.getLogger(__name__)

# 一字の名前(「環」など)は普通の語に紛れるので拾わない
_MIN_NAME_LENGTH = 2
# この字種どうしが続くと一つの語になる。ひらがなは助詞が続くので含めない
_WORD_SCRIPTS = ("katakana", "kanji", "alnum")


def _script(char: str) -> str:
    code = ord(char)
    if 0x30A1 <= code <= 0x30FA or char == "ー":
        return "katakana"
    if 0x3041 <= code <= 0x3096:
        return "hiragana"
    if 0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF or char in "々〆":
        return "kanji"
    if char.isalnum():
        return "alnum"
    return "other"


def _joined(neighbor: str | None, edge: str) -> bool:
    if neighbor is None:
        return False
    script = _script(neighbor)
    return script == _script(edge) and script in _WORD_SCRIPTS


def named_in(text: str, name: str) -> bool:
    """前後が名前の端と同じ字種で続く所は、別の語の一部とみなす(「セラ」と「セラフィナ」、「環」と「環境」)。"""
    start = text.find(name)
    while start != -1:
        end = start + len(name)
        before = text[start - 1] if start > 0 else None
        after = text[end] if end < len(text) else None
        if not _joined(before, name[0]) and not _joined(after, name[-1]):
            return True
        start = text.find(name, start + 1)
    return False


def cast_characters(episode: Episode) -> list[Character]:
    """`episode_characters` と `EpisodeCharacter.character` を読んだ話から。"""
    return [link.character for link in episode.episode_characters if not link.mentioned]


def mentioned_in(episode: Episode) -> list[Character]:
    """`episode_characters` と `EpisodeCharacter.character` を読んだ話から。"""
    return [link.character for link in episode.episode_characters if link.mentioned]


def named_characters(s: Session) -> list[Named]:
    """名前で拾える人物・対象。名前しか使わないので、人物の selectin の子の表は読まない。"""
    rows = s.execute(select(Character.id, Character.name).where(Character.name.is_not(None)).order_by(Character.id)).all()
    return [Named(id=row.id, name=row.name) for row in rows if len(row.name) >= _MIN_NAME_LENGTH]


def _planet_id(s: Session, location_id: int) -> int | None:
    return next((step.id for step in common_query.location_path(s, location_id) if step.kind == "星"), None)


def _elsewhere(s: Session, character_id: int, planet_id: int, time: Stamp) -> bool:
    """その時刻の居場所がどれも別の星にある人物。居場所が無いか、星の分からない居場所があれば別とは言えないので拾う。"""
    planets = [_planet_id(s, row.location_id)
               for row in s.scalars(common_query.character_location_select(character_id, time))]
    return bool(planets) and all(planet is not None and planet != planet_id for planet in planets)


def save_mentions(s: Session, episode_id: int, characters: list[Named] | None = None) -> list[int]:
    """名前だけ出る人物の行を、今のプロット・本文から拾った人物で置き換え、その人物の id を返す。
    何話も続けて拾い直すときは、`named_characters` を一度だけ読んで渡す。"""
    episode = s.get_one(Episode, episode_id)
    cast_ids = set(s.scalars(select(EpisodeCharacter.character_id).where(
        EpisodeCharacter.episode_id == episode_id, EpisodeCharacter.mentioned.is_(False))).all())
    text = "\n".join([episode.plot_text, episode.main_text])
    found = [character for character in (named_characters(s) if characters is None else characters)
             if character.id not in cast_ids and character.name and named_in(text, character.name)]
    planet_id = _planet_id(s, episode.location_id) if episode.location_id is not None else None
    if planet_id is not None and episode.start is not None:
        found = [character for character in found if not _elsewhere(s, character.id, planet_id, episode.start)]
    s.execute(delete(EpisodeCharacter).where(EpisodeCharacter.episode_id == episode_id, EpisodeCharacter.mentioned))
    s.add_all([EpisodeCharacter(episode_id=episode_id, character_id=character.id, mentioned=True)
               for character in found])
    s.flush()
    logger.info(f"話 id={episode_id} に名前だけ出る人物: {', '.join(str(character.name) for character in found) or 'なし'}")
    return [character.id for character in found]
