#!/usr/bin/env python3
"""本文への反応(ユーザが書く本文の差分を、語り部と人物役が読んで返す)を、手元でも web のセッションでも同じコマンドで扱う。

呼び分けと待ち方は `tool.episode_session` と同じ。待つコマンドは、新しい差分が来るまで表を一定の間隔で見て、来たら JSON を出して終わる。

    人物役: knowledge / text / wait-diff / react
    語り部: text / wait-diff / react(材料はスキルが読んで渡す)
    スキル: latest / close

    .venv/bin/python -m tool.episode_comment wait-diff --episode 102 --after 0
"""
from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from data_access_logic.logs import configure_logging
from tool.episode_session import _waited, call


def wait_diff(episode_id: int, after: int, interval: float, timeout: float) -> dict[str, Any]:
    """`after` より新しい差分が来たら、溜まっていた分をまとめて返す。終わりの合図があれば closed。"""
    def check():
        diffs = call("episode_comment.read_diffs_since.ReadDiffsSince", {"episode_id": episode_id, "after_diff_id": after})
        if not diffs:
            return None
        if any(diff["closing"] for diff in diffs):
            return {"status": "closed"}
        return {"status": "diff", "diffs": [{"id": diff["id"], "diff": diff["diff_text"]} for diff in diffs]}
    return _waited(check, interval, timeout) or {"status": "timeout"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    knowledge = commands.add_parser("knowledge", help="人物が、話の時刻に知ることのできるデータを読む")
    knowledge.add_argument("--episode", type=int, required=True)
    knowledge.add_argument("--character", type=int, required=True)

    text = commands.add_parser("text", help="いま保存されている本文の全文を読む")
    text.add_argument("--episode", type=int, required=True)

    wait = commands.add_parser("wait-diff", help="--after より新しい差分(diff)か、書き終えた合図(closed)が来るまで待つ")
    wait.add_argument("--episode", type=int, required=True)
    wait.add_argument("--after", type=int, required=True)
    wait.add_argument("--interval", type=float, default=1.0)
    wait.add_argument("--timeout", type=float, default=3000.0)

    react = commands.add_parser("react", help="差分への反応を足す")
    react.add_argument("--diff", type=int, required=True, help="読んだ差分のうち一番新しい id")
    react.add_argument("--character", type=int, help="人物の id。語り部は付けない")
    react.add_argument("--stance", required=True, choices=["感想", "同意", "反対", "修正案"])
    react.add_argument("--quote", help="反応する本文の箇所(本文からそのまま引く)")
    react.add_argument("--text", required=True)

    latest = commands.add_parser("latest", help="話の一番新しい差分の id(無ければ 0)")
    latest.add_argument("--episode", type=int, required=True)

    close = commands.add_parser("close", help="書き終えた合図を足し、語り部と人物役を止める")
    close.add_argument("--episode", type=int, required=True)

    args = parser.parse_args()
    configure_logging()
    # 待つあいだの呼び出しごとのログが、読む側の出力に積もって入力のトークンを食う
    logging.getLogger("httpx").setLevel(logging.WARNING)
    match args.command:
        case "knowledge":
            result = call("character.read_knowledge.ReadKnowledge", {"character_id": args.character, "episode_id": args.episode})
        case "text":
            [episode] = call("episode.read_episode_texts.ReadEpisodeTexts", {"episode_ids": [args.episode]})
            result = {"title": episode["title"], "main_text": episode["main_text"]}
        case "wait-diff":
            result = wait_diff(args.episode, args.after, args.interval, args.timeout)
        case "react":
            fields = {"diff_id": args.diff, "character_id": args.character, "stance": args.stance,
                      "quote": args.quote, "text": args.text}
            record = call("episode_comment.add_reaction.AddReaction",
                          {"reaction": {name: value for name, value in fields.items() if value is not None}})
            result = {"id": record["id"]}
        case "latest":
            result = call("episode_comment.read_latest_diff.ReadLatestDiff", {"episode_id": args.episode})
        case "close":
            result = call("episode_comment.close_comment.CloseComment", {"episode_id": args.episode})
        case _:
            parser.error(f"知らないコマンド: {args.command}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
