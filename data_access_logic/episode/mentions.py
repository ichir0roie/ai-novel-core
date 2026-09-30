#!/usr/bin/env python3
"""話に名前だけ出る人物(`episode_character.mentioned`)を、プロット・本文から拾い直す。

登場人物(`mentioned` でない行)は作者が決めるので触らない。拾うのは、承認済みの人物・対象のうち、
登場人物でなく、名前がプロット・本文に語として出るもの。
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db.schema import Character, ConfirmStatus, Episode, EpisodeCharacter

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


def mentioned_characters(s: Session, episode: Episode, cast_ids: set[int]) -> list[Character]:
    text = "\n".join([episode.plot_text, episode.main_text])
    candidates = s.scalars(
        select(Character)
        .where(Character.confirmed == ConfirmStatus.APPROVED, Character.name.is_not(None))
        .order_by(Character.id)
    ).all()
    return [
        character for character in candidates
        if character.id not in cast_ids and character.name
        and len(character.name) >= _MIN_NAME_LENGTH and named_in(text, character.name)
    ]


def save_mentions(s: Session, episode_id: int) -> None:
    """名前だけ出る人物の行を、今のプロット・本文から拾った人物で置き換える。"""
    episode = s.get_one(Episode, episode_id)
    cast_ids = set(s.scalars(select(EpisodeCharacter.character_id).where(
        EpisodeCharacter.episode_id == episode_id, EpisodeCharacter.mentioned.is_(False))).all())
    characters = mentioned_characters(s, episode, cast_ids)
    s.execute(delete(EpisodeCharacter).where(EpisodeCharacter.episode_id == episode_id, EpisodeCharacter.mentioned))
    s.add_all([EpisodeCharacter(episode_id=episode_id, character_id=character.id, mentioned=True)
               for character in characters])
    s.flush()
    logger.info(f"話 id={episode_id} に名前だけ出る人物: {', '.join(str(character.name) for character in characters) or 'なし'}")
