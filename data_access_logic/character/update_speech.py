#!/usr/bin/env python3
"""人物が話で言ったセリフの行を一つ、id で指して直す。渡した欄(原文・鮮明・あやふや)だけを直す。
セリフの行は本文を直しても残るので、推敲で本文のセリフを変え、人物役に古い言い回しを覚えさせたくないときに使う。
行の id は表 `character_speech` を話(`episode_id`)と人物(`character_id`)で引いて読む。

    UpdateCharacterSpeech(character_speech_id=12, speech=CharacterSpeechChange(verbatim="明日の朝に来い")).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.character.form import CharacterSpeechChange
from data_access_logic.character.record import CharacterSpeechRow
from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.query import common_query
from db.schema import CharacterSpeech


class UpdateCharacterSpeech(CommitEntrypoint):
    def __init__(self, character_speech_id: int, speech: CharacterSpeechChange):
        self.character_speech_id = character_speech_id
        self.speech = speech

    def execute(self, s: Session) -> CharacterSpeechRow:
        row = common_query.get_row(s, CharacterSpeech, self.character_speech_id)
        for name in self.speech.model_fields_set:
            setattr(row, name, getattr(self.speech, name))
        self.finalize(s, row)
        return CharacterSpeechRow.model_validate(row)
