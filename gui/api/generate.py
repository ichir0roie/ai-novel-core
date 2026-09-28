#!/usr/bin/env python3
"""「AI で作成」「AI で補完」のボタン。テーブルごとに、欄の値(下書き)を核に AI が全欄を組み立て直して行を足す
(`mode="edit"` / `"both"` なら、既存行の本文が空のときに限り、その行の本文だけを埋める)入口を結ぶ。

入口は `ai/claude_code/interface/` の `Generate*`(claude を叩くので Claude Code の環境でだけ、裏の job として走る)。
下書きは入口の第一引数に、`params` の値はそのままの名前で入口の引数に渡す。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai.claude_code import ai_client
from gui.api.models import ColumnMeta, GeneratorMeta


@dataclass(frozen=True)
class Generator:
    table: str
    key: str
    label: str
    entrance: str
    # 入口が下書きを受け取る引数の名前
    draft_arg: str
    mode: str = "create"
    when_empty: str | None = None
    when_not_empty: str | None = None
    params: tuple[ColumnMeta, ...] = field(default_factory=tuple)
    # true なら「AI で作成」の小さなボタン列には出さず、左の欄の一番下に大きく開く専用パネル(GUI 側)で出す
    # (推敲は指示文を書き込みながら本文も見たいので、他の AI 生成とは別の場所に大きく開く)
    panel: bool = False

    def to_meta(self) -> GeneratorMeta:
        return GeneratorMeta(key=self.key, label=self.label, entrance=self.entrance, mode=self.mode,
                             when_empty=self.when_empty, when_not_empty=self.when_not_empty,
                             params=list(self.params), panel=self.panel)


_CHARACTER_IDS = ColumnMeta(key="character_ids", label="登場人物", type="id_list", nullable=True, required=False,
                            references="character", comment="この話に出す人物。空ならその時刻に生きているメインキャラクター")
_PREVIOUS_EPISODE_IDS = ColumnMeta(
    key="previous_episode_ids", label="直前の話", type="id_list", nullable=True, required=False,
    references="episode", comment="概要と文体の覚え書きで渡す話。空なら作品の中でその時刻より前の三話")
# 推敲の指示文。大きなマークダウンの欄(section)で必須にする(本文が空のときの「AI で書く」と違い、
# 推敲は必ず観点を指示するので、空なら文体の好みに沿って見直すだけ、という省略は無くした)
_INSTRUCTION = ColumnMeta(key="instruction", label="Instruction", type="string", nullable=False, required=True,
                          section=True, comment="どこをどう直すか(例: 初登場キャラの外見・性格を厚く書く)")
_MODEL_PARAM = ColumnMeta(key="model", label="本文のモデル", type="string", nullable=True, required=False,
                          choices=list(ai_client.AVAILABLE_MODELS), default=ai_client.EPISODE_MODEL)
_EFFORT_PARAM = ColumnMeta(key="effort", label="本文の effort", type="string", nullable=True, required=False,
                           choices=list(ai_client.AVAILABLE_EFFORTS), default=ai_client.EPISODE_EFFORT)

GENERATORS: tuple[Generator, ...] = (
    Generator("character", "ai", "AI で作成", "randomizer.generate_character.GenerateCharacter", "character",
              params=(ColumnMeta(key="time", label="現在の時刻", type="stamp", nullable=True, required=False,
                                 comment="この時刻に生きている人物として作る。空なら世界の最新の出来事の時刻"),)),
    Generator("character", "complete", "AI で補完", "randomizer.generate_character.GenerateCharacter", "character",
              mode="edit", when_empty="text"),
    Generator("event", "ai", "AI で作成", "randomizer.generate_event.GenerateEvent", "event"),
    Generator("event", "complete", "AI で補完", "randomizer.generate_event.GenerateEvent", "event",
              mode="edit", when_empty="text"),
    Generator("episode", "frame", "AI で枠を作る", "story.generate_frame.GenerateFrame", "frame",
              params=(_CHARACTER_IDS, _PREVIOUS_EPISODE_IDS)),
    Generator("episode", "episode", "AI で本文まで書く", "story.generate_episode.GenerateEpisode", "episode",
              mode="both", when_empty="text",
              params=(_CHARACTER_IDS, _PREVIOUS_EPISODE_IDS, _MODEL_PARAM, _EFFORT_PARAM)),
    # 登場人物・直前の話は聞かず、既定(話の start に生きているメインキャラクター・その時刻より前の三話)を使う
    # (ReviseEpisode 側で解決する)。GUI の専用レイアウト(RevisePanel)は指示文・モデル・effort だけを出す
    Generator("episode", "revise", "AI で推敲する", "story.revise_episode.ReviseEpisode", "episode",
              mode="edit", when_not_empty="text", panel=True,
              params=(_INSTRUCTION, _MODEL_PARAM, _EFFORT_PARAM)),
)


def generators_of(table: str) -> list[Generator]:
    return [generator for generator in GENERATORS if generator.table == table]


def generator_of(table: str, key: str) -> Generator:
    for generator in generators_of(table):
        if generator.key == key:
            return generator
    raise KeyError(f"{table} に {key} という AI 生成は無い")


def _cleaned(value: Any) -> Any:
    """空の欄(None・空文字・空の配列)は「指定なし」なので渡さない。子の一覧は行ごとに同じ掃除をする。"""
    if isinstance(value, dict):
        return {key: _cleaned(item) for key, item in value.items() if item not in (None, "", [])}
    if isinstance(value, list):
        return [_cleaned(item) for item in value]
    return value


def build_args(generator: Generator, draft: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    known = {param.key for param in generator.params}
    unknown = set(args) - known
    if unknown:
        raise ValueError(f"{generator.table}/{generator.key} に無い指定: {sorted(unknown)}")
    return {generator.draft_arg: _cleaned(draft), **_cleaned(args)}
