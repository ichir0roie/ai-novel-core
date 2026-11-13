#!/usr/bin/env python3
"""話のあとに、登場人物ごとの差分(この話で起きたこと・知ったこと、知り合った相手、身に着けた・外した物、移った住まい)と、
登場人物が言ったセリフを、AI を挟まずに db へ入れる(`data_access_logic/readme.md` の「話の差分」)。

差分は、手番を回した話では人物役が自分の演じた手番から書き(`tool.episode_session close`)、手番を回していない話では
AI が本文から一度に書く(`outcomes_draft`、流れ `flows/episode.py` の `reflect_episode`)。どちらも同じ形で `apply_outcomes` に渡す。
当てられない値(装いに無い物・候補に無い場所・登場人物でない相手)は入れずに `skipped` に返し、損失として許す。
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_access_logic.ai_client import AIClient
from data_access_logic.character.commit_character_relation import CommitCharacterRelation
from data_access_logic.character.commit_character_skill import CommitCharacterSkill
from data_access_logic.character.form import CharacterRelationCreateForm, CharacterSkillCreateForm
from data_access_logic.character.moves import move_destinations, update_locations
from data_access_logic.character.record import (
    CharacterHistoryRow, CharacterMove, CharacterRelationHistoryRow, CharacterSkillHistoryRow,
)
from data_access_logic.episode.material import load_episode
from data_access_logic.episode.mentions import cast_characters
from data_access_logic.material import Material
from data_access_logic.query import common_query
from db.child_lists import appended_history
from db.schema import (
    Character, CharacterHistory, CharacterSkill, CharacterSkillHistory, CharacterSpeech, Location, StyleScope,
    summary_source_hash,
)
from db.stamp import Stamp

logger = logging.getLogger(__name__)

WORN_KIND = "装い"

_SYSTEM = """\
話の本文と登場人物を渡すので、登場人物ごとに、この話の前と後で変わったこと(差分)を返す。
- 来歴(histories)は、その人物がこの話でしたこと・起きたこと・知ったことを、一つの出来事につき一行で書く。本人だけが知る行になるので、
  ほかの人物の秘密を知ったなら、知った人物の行に「誰の何を知ったか」を書く(秘密を持つ人物の行には書かない)。
- 知り合った相手(met)は、この話で初めて言葉を交わした・名乗り合った相手だけ。すでにある関係の相手は挙げない。
- 身に着けた・手にした物(worn)と、外した・手放した・壊れた物(removed)は、人から見て分かる物だけ。removed は「今の装い」にある名前から選ぶ。
- 住まい・拠点を移したときだけ moved_to に移動先の候補の名前を書く。
- 人物は登場人物の人物idからだけ選ぶ。変わったことの無い人物は挙げない。"""


class MetCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="この話で初めて知り合った相手の人物id")
    relation: str = Field(min_length=1, description="本人から見た相手の、短い関係の名前")
    history: str = Field(min_length=1, description="この話で二人のあいだに起きたこと")


class WornItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="身に着けた・手にした物の名前")
    description: str = Field(min_length=1, description="どうしたか(手にした・羽織った・受け取ったなど)と、物の今の姿")


class CharacterOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int = Field(description="人物id")
    histories: list[str] = Field(default=[], description="この話でしたこと・起きたこと・知ったことの来歴の行。一つの出来事につき一行")
    met: list[MetCharacter] = Field(default=[], description="この話で初めて知り合った相手")
    worn: list[WornItem] = Field(default=[], description="この話で身に着けた・手にした、人から見て分かる物")
    removed: list[str] = Field(default=[], description="この話で外した・手放した・壊れた物の名前(今の装いの名前)")
    moved_to: str | None = Field(default=None, description="住まい・拠点を移した先の場所の名前。移していなければ空")


class OutcomesDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcomes: list[CharacterOutcome] = Field(description="登場人物ごとの差分。変わったことのある人物だけ")


class SessionSpeech(BaseModel):
    character_id: int
    text: str


class OutcomesForm(BaseModel):
    episode_id: int
    outcomes: list[CharacterOutcome]
    # 話のセッションの行の、登場人物が言ったセリフ(手番の順)。None なら今の行をそのまま残す
    speeches: list[SessionSpeech] | None = None


class AppliedOutcomes(Material):
    histories: int = 0
    # 「誰から→誰へ: 関係」
    relations: list[str] = []
    # 「人物: 物」
    worn: list[str] = []
    removed: list[str] = []
    # 「人物 → 場所」
    moves: list[str] = []
    speeches: int = 0
    # 当てられずに入れなかったもの
    skipped: list[str] = []


def _worn_skills(s: Session, character_id: int) -> list[CharacterSkill]:
    return [skill for skill in s.scalars(common_query.character_skills_select(character_id)).all()
            if skill.kind == WORN_KIND]


def _active_history(skill: CharacterSkill, time: Stamp) -> CharacterSkillHistory | None:
    return next((history for history in skill.histories if history.covers(time)), None)


def _wear(s: Session, character: Character, item: WornItem, time: Stamp, applied: AppliedOutcomes) -> None:
    """同じ名前の装いがあれば、外していればその来歴に着けた行を足し、着けたままなら何もしない。無ければ装いを足す。"""
    skill = next((skill for skill in _worn_skills(s, character.id) if skill.name == item.name), None)
    row = CharacterSkillHistoryRow(start=time, description=item.description)
    if skill is None:
        CommitCharacterSkill(CharacterSkillCreateForm(
            character_id=character.id, name=item.name, kind=WORN_KIND, text=item.description, histories=[row])).execute(s)
    elif _active_history(skill, time) is None:
        history = appended_history(row, CharacterSkillHistory, owner=character)
        history.character_skill_id = skill.id
        s.add(history)
    else:
        return
    applied.worn.append(f"{character.name}: {item.name}")


def _remove(s: Session, character: Character, name: str, time: Stamp, applied: AppliedOutcomes) -> None:
    skill = next((skill for skill in _worn_skills(s, character.id) if skill.name == name), None)
    history = None if skill is None else _active_history(skill, time)
    if history is None:
        applied.skipped.append(f"{character.name}の外した物「{name}」は、今の装いに無い")
        return
    history.end = time
    applied.removed.append(f"{character.name}: {name}")


def _destination(s: Session, location_id: int | None, time: Stamp, name: str) -> int | None:
    """話の場所から届く移動先の候補のうち、名前の同じ場所。候補に無ければ、名前の同じ場所が一つだけのときその場所。"""
    if location_id is not None:
        for destination in move_destinations(s, location_id, time):
            if destination.name == name:
                return destination.id
    found = s.scalars(select(Location.id).where(Location.name == name)).all()
    return found[0] if len(found) == 1 else None


def _relate(s: Session, character: Character, met: MetCharacter, cast: dict[int, Character], time: Stamp,
            applied: AppliedOutcomes) -> None:
    partner = cast.get(met.character_id)
    if partner is None or partner.id == character.id:
        applied.skipped.append(f"{character.name}が知り合った人物 id={met.character_id} は、ほかの登場人物でない")
        return
    existing = s.scalars(common_query.character_relations_at_select([character.id], time)).all()
    if any(row.character_1_id == character.id and row.character_2_id == partner.id for row in existing):
        return
    CommitCharacterRelation(CharacterRelationCreateForm(
        character_1_id=character.id, character_2_id=partner.id, relation=met.relation, text=met.relation, start=time,
        histories=[CharacterRelationHistoryRow(start=time, description=met.history)])).execute(s)
    applied.relations.append(f"{character.name}→{partner.name}: {met.relation}")


def apply_outcomes(s: Session, form: OutcomesForm) -> AppliedOutcomes:
    """差分を話の時刻で入れる。来歴は本人だけが知る行にし(ほかの人物の秘密を知ったなら、知った人物の行。秘密を持つ人物の行には
    触れない)、知り合った相手は本人から相手への向きの関係を足す(すでにあれば足さない)。本文を確定してから呼ぶ。"""
    episode = load_episode(s, form.episode_id)
    time = episode.start
    if time is None or not episode.main_text.strip():
        raise ValueError(f"話 id={episode.id} は時刻か本文が空。本文を確定してから差分を入れる")
    cast = {character.id: character for character in cast_characters(episode)}
    applied = AppliedOutcomes()
    for outcome in form.outcomes:
        character = cast.get(outcome.character_id)
        if character is None:
            applied.skipped.append(f"人物 id={outcome.character_id} は話 id={episode.id} の登場人物でない")
            continue
        for description in outcome.histories:
            if description.strip():
                history = appended_history(CharacterHistoryRow(start=time, description=description), CharacterHistory,
                                           owner=character)
                history.character_id = character.id
                s.add(history)
                applied.histories += 1
        for met in outcome.met:
            _relate(s, character, met, cast, time, applied)
        for item in outcome.worn:
            _wear(s, character, item, time, applied)
        for name in outcome.removed:
            _remove(s, character, name, time, applied)
        if outcome.moved_to:
            location_id = _destination(s, episode.location_id, time, outcome.moved_to)
            if location_id is None:
                applied.skipped.append(f"{character.name}の移動先「{outcome.moved_to}」が、名前で一つに決まらない")
            else:
                update_locations(s, [CharacterMove(character_id=character.id, location_id=location_id)], time)
                applied.moves.append(f"{character.name} → {outcome.moved_to}")
    if form.speeches is not None:
        applied.speeches = _save_speeches(s, episode.id, episode.main_text, form.speeches, cast)
    s.flush()
    return applied


def _save_speeches(s: Session, episode_id: int, main_text: str, speeches: list[SessionSpeech],
                   cast: dict[int, Character]) -> int:
    """話の行を置き換える。覚え(鮮明・あやふや)も言ったとおりにする(本文から AI で作り直さない損失は許す)。"""
    for row in s.scalars(select(CharacterSpeech).where(CharacterSpeech.episode_id == episode_id)).all():
        s.delete(row)
    kept = [speech for speech in speeches if speech.character_id in cast and speech.text.strip()]
    source_hash = summary_source_hash(main_text)
    s.add_all(CharacterSpeech(episode_id=episode_id, character_id=speech.character_id, position=position,
                              verbatim=speech.text, vivid=speech.text, vague=speech.text, source_hash=source_hash)
              for position, speech in enumerate(kept))
    return len(kept)


class OutcomeMember(Material):
    id: int
    name: str | None = None
    # 話の時刻に身に着けている装いの名前
    worn: list[str] = []


class ReflectMaterial(Material):
    """本文から差分を書かせる材料。本文・時刻・登場人物が無ければ作らない。"""

    episode_id: int
    main_text: str
    cast: list[OutcomeMember]
    destinations: list[str]


class ReflectMaterialSerialized(ReflectMaterial):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> dict[str, Any]:
        return {"登場人物": [{"人物id": member.id, "名前": member.name, "今の装い": member.worn} for member in self.cast],
                "移動先の候補": self.destinations, "本文": self.main_text}


def reflect_material(s: Session, episode_id: int) -> ReflectMaterial | None:
    episode = load_episode(s, episode_id)
    time = episode.start
    characters = cast_characters(episode)
    if time is None or not episode.main_text.strip() or not characters:
        return None
    return ReflectMaterial(
        episode_id=episode.id, main_text=episode.main_text,
        cast=[OutcomeMember(id=character.id, name=character.name,
                            worn=[skill.name for skill in _worn_skills(s, character.id)
                                  if _active_history(skill, time) is not None])
              for character in characters],
        destinations=[] if episode.location_id is None else
        [destination.name for destination in move_destinations(s, episode.location_id, time) if destination.name])


def outcomes_draft(ai: AIClient, material: ReflectMaterial) -> list[CharacterOutcome]:
    """AI が答えなければ空(差分は入れない)。"""
    draft = ai.generate(
        "\n".join([ReflectMaterialSerialized.model_validate(material).model_dump_json(indent=2),
                   "登場人物ごとに、この話の差分を返す。"]),
        OutcomesDraft, system=_SYSTEM, style_scope=StyleScope.HISTORY)
    if draft is None:
        logger.warning(f"話 id={material.episode_id} の差分が得られなかったので、人物の設定は変えない")
        return []
    return draft.outcomes
