#!/usr/bin/env python3
"""人物モード(`SimulateDay`)を、テスト用の db と本物の AI(`claude -p`)で回し、ロジックとかかった手間を報告する。

パターン(`tool.test.day_world.PATTERNS`)の世界を作り、続けて何日か回して、日ごとに次を出す。

- かかった時間、AI の呼び出し(モデルごとの回数・待ち時間・入力/キャッシュ/出力のトークン・問いの字数)、db の段の回数と時間
- 人物ごとの一時間ごとの行動(種別・場所・行動量・欲)、眠った時間と起きた時刻、満ち足り方、欲のモチベーション、一日の出来事

    .venv/bin/python -m tool.test.run_day --pattern basic --days 2 --out <dir>

AI を本当に呼ぶので、使用量を使う。
"""
from __future__ import annotations

from tool.test import ensure_test_db  # schema より先に読む(db をテスト用の db に固定する)

import argparse
import json
import subprocess
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select

from data_access_logic import step
from data_access_logic.caller import calling
from data_access_logic.flows import act
from data_access_logic.logs import configure_logging
from db.schema import CharacterDay, CharacterMotivation, Event, EventAction, Expansion, Location, get_env_session
from db.stamp import Stamp
from tool.test.day_world import PATTERNS, build_day_world

_lock = threading.Lock()
_ai_calls: list[dict[str, Any]] = []
_steps: dict[str, list[float]] = defaultdict(list)
_original_run = subprocess.run


def _watched_run(args, *rest, **kwargs):
    """`claude -p` の呼び出しだけ、待ち時間と使ったトークンを控える。"""
    if not (isinstance(args, list) and args and "-p" in args):
        return _original_run(args, *rest, **kwargs)
    started = time.monotonic()
    completed = _original_run(args, *rest, **kwargs)
    seconds = time.monotonic() - started
    usage: dict[str, Any] = {}
    try:
        usage = json.loads(completed.stdout).get("usage", {})
    except (ValueError, AttributeError):
        pass
    model = args[args.index("--model") + 1] if "--model" in args else ""
    with _lock:
        _ai_calls.append({
            "model": model, "seconds": seconds, "resumed": "--resume" in args, "prompt_letters": len(kwargs.get("input") or ""),
            "input": usage.get("input_tokens", 0), "cache_read": usage.get("cache_read_input_tokens", 0),
            "cache_write": usage.get("cache_creation_input_tokens", 0), "output": usage.get("output_tokens", 0)})
    return completed


def _timed_step(step_function, form=None):
    started = time.monotonic()
    try:
        return step.run(step_function, form)
    finally:
        with _lock:
            _steps[step.step_id(step_function)].append(time.monotonic() - started)


def _ai_report() -> dict[str, Any]:
    by_model: dict[str, Counter] = defaultdict(Counter)
    for call in _ai_calls:
        kind = f"{call['model']}{' (続き)' if call['resumed'] else ''}"
        row = by_model[kind]
        row["calls"] += 1
        for key in ("seconds", "prompt_letters", "input", "cache_read", "cache_write", "output"):
            row[key] += call[key]
    return {kind: {**{key: round(value) for key, value in row.items()},
                   "seconds_per_call": round(row["seconds"] / row["calls"], 1),
                   "letters_per_call": round(row["prompt_letters"] / row["calls"])}
            for kind, row in by_model.items()}


def _step_report() -> list[dict[str, Any]]:
    rows = [{"step": name, "calls": len(times), "seconds": round(sum(times), 1)} for name, times in _steps.items()]
    return sorted(rows, key=lambda row: -row["seconds"])[:8]


def _character_report(character_id: int, day_start: Stamp, day_end: Stamp, expansion_id: int | None,
                      event_id: int | None) -> dict[str, Any]:
    with get_env_session() as s:
        actions = s.scalars(select(EventAction).where(
            EventAction.character_id == character_id, EventAction.time >= day_start, EventAction.time < day_end)
            .order_by(EventAction.time)).all()
        names = {row.id: row.name for row in s.scalars(select(Location).where(
            Location.id.in_({action.location_id for action in actions}))).all()}
        day = s.scalars(select(CharacterDay).where(CharacterDay.character_id == character_id,
                                                   CharacterDay.date == day_start)).first()
        wants = s.scalars(select(CharacterMotivation).where(
            CharacterMotivation.character_id == character_id, CharacterMotivation.start <= day_start,
            (CharacterMotivation.end.is_(None)) | (CharacterMotivation.end > day_start))).all()
        expansion = None if expansion_id is None else s.get(Expansion, expansion_id)
        event = None if event_id is None else s.get(Event, event_id)
        hours = [f"{action.time.digits[3]:>2}時 {action.kind:<4} {names.get(action.location_id, '')} "
                 f"L{action.load} 空{action.hunger} 人{action.desire} 眠{action.sleepiness} | "
                 f"{action.text.replace(chr(10), ' / ')[:90]}" for action in actions]
        kinds = Counter(action.kind for action in actions)
        return {
            "hours": hours, "kinds": dict(kinds),
            "day": None if day is None else {"food": day.food, "sleep": day.sleep, "touch": day.touch, "load": day.load,
                                             "bedtime": day.bedtime},
            "motivations": [f"{row.text}({row.strength})" for row in wants],
            "event": None if event is None else {"name": event.name, "text": event.text},
            "summary": None if expansion is None else expansion.summary,
        }


def run_days(pattern: str, days: int, seed: int, out: Path) -> list[dict[str, Any]]:
    world = build_day_world(PATTERNS[pattern])
    reports = []
    date: str | None = world.date
    for index in range(days):
        _ai_calls.clear()
        _steps.clear()
        started = time.monotonic()
        with calling(_timed_step):
            run = act.simulate_day(world.character_ids, date, seed=seed + index)
        elapsed = time.monotonic() - started
        assert run.date is not None and run.day_end is not None
        acted = {item.character_id: item for item in run.acted}
        # 時刻は人物の暦で読む(一日の長さが違う暦では、`Stamp.plus_days` で日の終わりを出すと次の日にならない)
        with run.scoped():
            report = {
                "pattern": pattern, "day": index + 1, "date": str(run.date), "seconds": round(elapsed),
                "failed": [failure.model_dump(mode="json") for failure in run.failed],
                "ai": _ai_report(), "steps": _step_report(),
                "characters": {str(character_id): _character_report(
                    character_id, run.date, run.day_end,
                    acted[character_id].expansion_id if character_id in acted else None,
                    acted[character_id].event.id if character_id in acted else None)
                    for character_id in world.character_ids},
            }
        reports.append(report)
        (out / f"{pattern}-day{index + 1}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                            encoding="utf-8")
        # 二日目からは、入口が人物の最後に出た日の翌日を選ぶ
        date = None
    return reports


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", choices=sorted(PATTERNS), default="basic")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    ensure_test_db()
    configure_logging()
    subprocess.run = _watched_run  # type: ignore[assignment]
    args.out.mkdir(parents=True, exist_ok=True)
    for report in run_days(args.pattern, args.days, args.seed, args.out):
        print(json.dumps({key: report[key] for key in ("pattern", "day", "date", "seconds", "failed", "ai")},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
