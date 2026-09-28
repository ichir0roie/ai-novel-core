#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code import ai_client
from ai.claude_code.claude_code_time_keeper import _writer_options
from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery
from ai.time_keeper import episode_generator, frame_generator
from data_access_logic.query import world_createion_query
from db.schema import Character, ConfirmStatus, Episode, Stamp


class GenerateEpisode(StoryQuery):
    """作者の下書き(GUI の欄の値。`story_id` 以外は空でもよい)から、話を一話ぶん(枠と本文)AI に書かせて足す。
    `id` を渡せばその枠(本文の無い話)へ本文を書く。

    種(`key`)と時刻(`start`)が下書きに揃っていれば、そのまま `write_episode`(常駐ループ側)と同じ生成で本文を書く。
    どちらかが空なら先に `GenerateFrame` と同じ生成で枠を決めてから本文を書く。
    `character_ids` を省けばその時刻に生きているメインキャラクター。`model` / `effort` は本文を書く呼び出しにだけ効く(省けば fable の high)。
    `shared_style_extra` / `style_extra` は世界ごとの文体の好み(世界リポジトリの `instructions/style.py`)。

    AI 呼び出し(数分〜十数分かかることがある)の前に、下書きの題・種・視点・場所・時刻を一度保存する。
    途中で失敗しても、この保存分(枠)は db に残る。
    """

    def __init__(self, episode: dict, character_ids: list[int] | None = None,
                 previous_episode_ids: list[int] | None = None, place_id: int | None = None,
                 model: str | None = None, effort: str | None = None, *,
                 shared_style_extra: str = "", style_extra: str = "", ai=ai_client):
        self.episode = dict(episode or {})
        self.character_ids = character_ids
        self.previous_episode_ids = previous_episode_ids
        self.place_id = place_id
        self.model = model
        self.effort = effort
        self.shared_style_extra = shared_style_extra
        self.style_extra = style_extra
        self.ai = ai

    def _writer_options(self) -> dict | None:
        if self.ai is ai_client:
            return _writer_options(self.model, self.effort)
        options = {key: value for key, value in (("model", self.model), ("effort", self.effort)) if value}
        return options or None

    @staticmethod
    def _main_characters(session, time: Stamp) -> list[int]:
        return list(session.scalars(
            world_createion_query.alive_characters_select(time)
            .where(Character.main_character.is_(True),
                   Character.confirmed == ConfirmStatus.APPROVED)
            .order_by(Character.id)).all())

    def execute(self, session) -> dict:
        draft = dict(self.episode)
        for key in ("letters", "synced", "text"):
            draft.pop(key, None)
        episode_id = draft.pop("id", None)
        slot = episode_generator.frame(session, episode_id) if episode_id is not None else None
        story_id = draft.get("story_id") or (slot.story_id if slot else None)
        if story_id in (None, ""):
            raise ValueError("story_id は必須")
        story_id = int(story_id)

        if slot is None:
            slot = Episode(story_id=story_id, title="", key="")
            session.add(slot)
        episode_generator.save_draft(session, slot, draft)

        key = (draft.get("key") or slot.key or "").strip()
        time = Stamp.parse(draft.get("start")) or slot.start
        if not key or time is None:
            slot = frame_generator.generate_frame(
                session, self.ai, story_id, draft, self.character_ids, self.previous_episode_ids,
                episode_id=slot.id)
            key, time = slot.key, slot.start

        character_ids = list(self.character_ids or [])
        if not character_ids:
            character_ids = [c.id for c in self._main_characters(session, time)]
        if not character_ids:
            raise ValueError("character_ids(登場人物)が空で、その時刻に生きているメインキャラクターも居ない")

        viewpoint = (draft.get("viewpoint") or "").strip() or None
        record = frame_generator.generate(
            session, self.ai, story_id, key, time, character_ids, self.previous_episode_ids,
            place_id=self.place_id, viewpoint=viewpoint, writer_options=self._writer_options(),
            episode_id=slot.id,
            shared_style_extra=self.shared_style_extra, style_extra=self.style_extra)
        if record is None:
            raise ValueError("本文が得られなかった")
        return _rows.episode_row(record)
