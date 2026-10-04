#!/usr/bin/env python3
"""話のセッション(語り部と人物役の手番)を、手元でも web のセッションでも同じコマンドで扱う。

手元は入口を直に回し、web のセッション(`CLAUDE_CODE_REMOTE=true`)は API の入口を呼ぶ。待つコマンドは、
返すものが来るまで表を一定の間隔で見て、来たら結果の JSON を出して終わる(待つあいだ Claude は考えない)。

    人物役: knowledge / wait-turn / answer
    語り部: stage / appearance / add / wait-answers / read / close
    演じ直す前: clear

    .venv/bin/python -m tool.episode_session wait-turn --episode 102 --character 1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from data_access_logic.logs import configure_logging


def call(entrance_id: str, args: dict[str, Any]) -> Any:
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        from web_session.api import run_entrance
        return run_entrance(entrance_id, args)
    from gui.api import interface
    entrance = interface.db_entrance_of(entrance_id)
    return interface.call(entrance, interface.prepare(entrance, args))


def _waited(check, interval: float, timeout: float) -> Any:
    """`check()` が None 以外を返すまで、`interval` 秒おきに呼ぶ。`timeout` 秒を過ぎたら None。"""
    deadline = time.monotonic() + timeout
    while True:
        found = check()
        if found is not None:
            return found
        if time.monotonic() + interval > deadline:
            return None
        time.sleep(interval)


def wait_turn(episode_id: int, character_id: int, interval: float, timeout: float) -> dict[str, Any]:
    def check():
        state = call("episode_session.read_turn.ReadTurn", {"episode_id": episode_id, "character_id": character_id})
        return state if state["status"] != "waiting" else None
    return _waited(check, interval, timeout) or {"status": "timeout"}


def wait_answers(episode_id: int, after: int, interval: float, timeout: float) -> dict[str, Any]:
    """手番がすべて埋まったら、`after` より後の行を返す。"""
    def check():
        records = call("episode_session.read_session.ReadSession", {"episode_id": episode_id})
        if any(record["action"] is None and not record["closing"] for record in records):
            return None
        return {"status": "answered", "records": [record for record in records if record["id"] > after]}
    return _waited(check, interval, timeout) or {"status": "timeout"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    knowledge = commands.add_parser("knowledge", help="人物が、話のセッションでいる時刻に知ることのできるデータを読む")
    knowledge.add_argument("--episode", type=int, required=True)
    knowledge.add_argument("--character", type=int, required=True)

    wait = commands.add_parser("wait-turn", help="自分の番(turn)か話の終わり(closed)が来るまで待つ")
    wait.add_argument("--episode", type=int, required=True)
    wait.add_argument("--character", type=int, required=True)

    answer = commands.add_parser("answer", help="自分の番の行に一手を入れる")
    answer.add_argument("--record", type=int, required=True)
    answer.add_argument("--action", required=True)
    answer.add_argument("--thought")
    answer.add_argument("--speech")
    answer.add_argument("--aim")

    appearance = commands.add_parser("appearance", help="初対面の相手から見て分かること(名前なし)を読む")
    appearance.add_argument("--character", type=int, required=True)
    appearance.add_argument("--time", required=True)

    stage = commands.add_parser("stage", help="語り部が読む材料(プロット・場所・登場人物・関係・設定と、その来歴・履歴を知る相手)を読む")
    stage.add_argument("--episode", type=int, required=True)

    add = commands.add_parser("add", help="手番の要求の行を足す(JSON の配列: character_id・time・request)")
    add.add_argument("--episode", type=int, required=True)
    add.add_argument("--turns", required=True, help="JSON のファイル。- なら標準入力から読む")
    add.add_argument("--wait", action="store_true", help="足したあと、手番がすべて埋まるまで待ち、足した行から後を返す")

    answers = commands.add_parser("wait-answers", help="手番がすべて埋まるまで待ち、--after より後の行を返す")
    answers.add_argument("--episode", type=int, required=True)
    answers.add_argument("--after", type=int, default=0)

    read = commands.add_parser("read", help="セッションの行をすべて読む")
    read.add_argument("--episode", type=int, required=True)

    close = commands.add_parser("close", help="出た人物すべてに終了の行を足す")
    close.add_argument("--episode", type=int, required=True)

    clear = commands.add_parser("clear", help="話のセッションの行をすべて消す(手番を演じ直す前に)")
    clear.add_argument("--episode", type=int, required=True)

    for waiting in (wait, answers, add):
        waiting.add_argument("--interval", type=float, default=1.0)
        waiting.add_argument("--timeout", type=float, default=3000.0)

    args = parser.parse_args()
    configure_logging()
    match args.command:
        case "knowledge":
            result = call("character.read_knowledge.ReadKnowledge", {"episode_id": args.episode, "character_id": args.character})
        case "wait-turn":
            result = wait_turn(args.episode, args.character, args.interval, args.timeout)
        case "answer":
            fields = {"thought": args.thought, "action": args.action, "speech": args.speech, "aim": args.aim}
            result = call("episode_session.answer_turn.AnswerTurn", {
                "record_id": args.record, "answer": {name: value for name, value in fields.items() if value is not None}})
        case "appearance":
            result = call("character.read_appearance.ReadAppearance", {"character_id": args.character, "time": args.time})
        case "stage":
            result = call("episode_session.read_stage.ReadStage", {"episode_id": args.episode})
        case "add":
            text = sys.stdin.read() if args.turns == "-" else Path(args.turns).read_text(encoding="utf-8")
            result = call("episode_session.add_turns.AddTurns", {"episode_id": args.episode, "turns": json.loads(text)})
            if args.wait and result:
                result = wait_answers(args.episode, min(record["id"] for record in result) - 1, args.interval, args.timeout)
        case "wait-answers":
            result = wait_answers(args.episode, args.after, args.interval, args.timeout)
        case "read":
            result = call("episode_session.read_session.ReadSession", {"episode_id": args.episode})
        case "close":
            result = call("episode_session.close_session.CloseSession", {"episode_id": args.episode})
        case "clear":
            result = call("episode_session.clear_session.ClearSession", {"episode_id": args.episode})
        case _:
            parser.error(f"知らないコマンド: {args.command}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
