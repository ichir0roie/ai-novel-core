#!/usr/bin/env python3
"""話のセッション(語り部と人物役の手番)を、手元でも web のセッションでも同じコマンドで扱う。

手元は入口を直に回し、web のセッション(`CLAUDE_CODE_REMOTE=true`)は API の入口を呼ぶ。待つコマンドは、
返すものが来るまで表を一定の間隔で見て、来たら結果の JSON を出して終わる(待つあいだ Claude は考えない)。

    人物役: knowledge / ideas / wait-turn / answer(--wait で、入れたあと次の番まで待つ)
    語り部: stage / appearance / add / add-ideas / wait-answers / read / close
    演じ直す前: clear

    .venv/bin/python -m tool.episode_session wait-turn --episode 102 --character 1
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from data_access_logic.logs import configure_logging


def call(entrance_id: str, args: dict[str, Any]) -> Any:
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        from web_session.transport import run_entrance
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


def _moment(args: argparse.Namespace) -> dict[str, Any]:
    """話か時刻の、渡された方だけ。`time` を知らない古い API にも、話で呼ぶぶんはそのまま通るように。"""
    return {"episode_id": args.episode} if args.episode is not None else {"time": args.time}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    knowledge = commands.add_parser("knowledge", help="人物が、話のセッションでいる時刻(--time なら、その時刻)に知ることのできるデータを読む")
    ideas = commands.add_parser("ideas", help="手番の要求に出た語を、人物が知っているアイデアから引く")
    for knowing in (knowledge, ideas):
        knowing.add_argument("--character", type=int, required=True)
        moment = knowing.add_mutually_exclusive_group(required=True)
        moment.add_argument("--episode", type=int)
        moment.add_argument("--time", help="話を渡さないときの時刻(スキル call-character で歳を言って呼ぶとき)")
    ideas.add_argument("--word", action="append", required=True, help="引く語。いくつも渡すなら --word を重ねる")

    wait = commands.add_parser("wait-turn", help="自分の番(turn)か話の終わり(closed)が来るまで待つ")
    wait.add_argument("--episode", type=int, required=True)
    wait.add_argument("--character", type=int, required=True)

    answer = commands.add_parser("answer", help="自分の番の行に一手を入れる")
    answer.add_argument("--record", type=int, required=True)
    answer.add_argument("--action", required=True)
    answer.add_argument("--thought")
    answer.add_argument("--speech")
    answer.add_argument("--aim")
    answer.add_argument("--wait", action="store_true", help="入れたあと、次の番か話の終わりまで待ち、wait-turn と同じ JSON を返す")
    answer.add_argument("--episode", type=int, help="--wait のときの話")
    answer.add_argument("--character", type=int, help="--wait のときの人物")

    appearance = commands.add_parser("appearance", help="初対面の相手から見て分かること(名前なし)を読む")
    appearance.add_argument("--character", type=int, required=True)
    appearance.add_argument("--time", required=True)

    stage = commands.add_parser("stage", help="語り部が読む材料(プロット・場所・登場人物の表層・知り合いの組)を読む")
    stage.add_argument("--episode", type=int, required=True)

    add = commands.add_parser("add", help="手番の要求の行を足す(JSON の配列: character_id・time・request)")
    add.add_argument("--episode", type=int, required=True)
    add.add_argument("--turns", required=True, help="JSON のファイル。- なら標準入力から読む")
    add.add_argument("--wait", action="store_true", help="足したあと、手番がすべて埋まるまで待ち、足した行から後を返す")

    add_ideas = commands.add_parser(
        "add-ideas", help="場面に出した新しい語をアイデアと照らし、当たらなければ候補として足す(JSON の配列: keyword・description・kind)")
    add_ideas.add_argument("--episode", type=int, required=True)
    add_ideas.add_argument("--ideas", required=True, help="JSON のファイル。- なら標準入力から読む")

    answers = commands.add_parser("wait-answers", help="手番がすべて埋まるまで待ち、--after より後の行を返す")
    answers.add_argument("--episode", type=int, required=True)
    answers.add_argument("--after", type=int, default=0)

    read = commands.add_parser("read", help="セッションの行をすべて読む")
    read.add_argument("--episode", type=int, required=True)

    close = commands.add_parser("close", help="出た人物すべてに終了の行を足す")
    close.add_argument("--episode", type=int, required=True)

    clear = commands.add_parser("clear", help="話のセッションの行をすべて消す(手番を演じ直す前に)")
    clear.add_argument("--episode", type=int, required=True)

    for waiting in (wait, answers, add, answer):
        waiting.add_argument("--interval", type=float, default=0.3)
        waiting.add_argument("--timeout", type=float, default=3000.0)

    args = parser.parse_args()
    if args.command == "answer" and args.wait and (args.episode is None or args.character is None):
        parser.error("answer --wait には --episode と --character が要る")
    configure_logging()
    # 待つあいだの呼び出しごとのログが、人物役・語り部の読む出力に積もって入力のトークンを食う
    logging.getLogger("httpx").setLevel(logging.WARNING)
    match args.command:
        case "knowledge":
            result = call("character.read_knowledge.ReadKnowledge", {"character_id": args.character, **_moment(args)})
        case "ideas":
            result = call("character.read_known_ideas.ReadKnownIdeas",
                          {"character_id": args.character, "words": args.word, **_moment(args)})
        case "wait-turn":
            result = wait_turn(args.episode, args.character, args.interval, args.timeout)
        case "answer":
            fields = {"thought": args.thought, "action": args.action, "speech": args.speech, "aim": args.aim}
            result = call("episode_session.answer_turn.AnswerTurn", {
                "record_id": args.record, "answer": {name: value for name, value in fields.items() if value is not None}})
            if args.wait:
                result = wait_turn(args.episode, args.character, args.interval, args.timeout)
        case "appearance":
            result = call("character.read_appearance.ReadAppearance", {"character_id": args.character, "time": args.time})
        case "stage":
            result = call("episode_session.read_stage.ReadStage", {"episode_id": args.episode})
        case "add":
            text = sys.stdin.read() if args.turns == "-" else Path(args.turns).read_text(encoding="utf-8")
            result = call("episode_session.add_turns.AddTurns", {"episode_id": args.episode, "turns": json.loads(text)})
            if args.wait and result:
                result = wait_answers(args.episode, min(record["id"] for record in result) - 1, args.interval, args.timeout)
        case "add-ideas":
            text = sys.stdin.read() if args.ideas == "-" else Path(args.ideas).read_text(encoding="utf-8")
            result = call("episode_session.add_ideas.AddIdeas", {"episode_id": args.episode, "ideas": json.loads(text)})
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
