#!/usr/bin/env python3
"""話のセッション(語り部と人物役の手番)を、手元でも web のセッションでも同じコマンドで扱う。

手元は入口を直に回し、web のセッション(`CLAUDE_CODE_REMOTE=true`)は API の入口を呼ぶ。
人物役は表を見張らない。語り部が番の行の id を人物役に送り、人物役はその行だけを読んで一手を入れる。
人物役がはじめに読む材料(knowledge・played)は標準出力に出さずファイルに書き、そのパスを出す(Read で最後まで読む)。

    人物役: knowledge / ideas / played / turn / answer
    語り部: knower-gaps / stage / appearance / add / add-ideas / moves / read
    作者と代わる代わる書く語り部: text / append / replace / hand-over(--wait で、作者が書くまで待つ)/ wait-author / author
    演じ直す前・作者と書き終えたとき: clear(--from で、その行から後だけ)

    .venv/bin/python -m tool.episode_session turn --episode 102 --character 1 --record 1290
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
from db.schema import SessionKind


# 長い Bash の結果は Claude Code が頭だけを見せてファイルに逃がし、人物役は逃がされた先を読み落としたまま演じた
# (知り合いを知らない人として返した)。人物の材料は数万字になるので、いつもファイルに書いて Read で読ませる
FILE_COMMANDS = ("knowledge", "played")
OUT_DIR = Path(__file__).resolve().parent.parent / ".cache" / "episode_session"


def call(entrance_id: str, args: dict[str, Any]) -> Any:
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        from web_session.transport import run_entrance
        return run_entrance(entrance_id, args)
    from gui.api import interface
    return interface.call(interface.db_entrance_class(entrance_id), args)


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


def read_turn(episode_id: int, character_id: int, record_id: int) -> dict[str, Any]:
    """語り部に番を知らされた人物役が、その行(見聞きしたことと要求)を読む。待たない。
    知らされた行がまだ番でない(前の手番が埋まっていない)か、別の行が番なら、そのことを返す。"""
    state = call("episode_session.read_turn.ReadTurn", {"episode_id": episode_id, "character_id": character_id})
    if state["status"] == "turn" and state["record"]["id"] != record_id:
        return {"status": "other", "record_id": state["record"]["id"]}
    return state


def _row(record: dict[str, Any]) -> dict[str, Any]:
    """語り部の読む行。人物は名前だけにし、見聞きする人物は id だけにする。"""
    return {"id": record["id"], "kind": record["kind"], "character": record["character"] and record["character"]["name"],
            "time": record["time"], "witnesses": [witness["character_id"] for witness in record["witnesses"]],
            "request": record["request"], "simultaneous": record["simultaneous"],
            **{name: record[name] for name in ("thought", "action", "speech", "aim")}}


def wait_author(episode_id: int, interval: float, timeout: float) -> dict[str, Any]:
    """作者が書く(一番新しい作者の行に行動が入る)まで待つ。"""
    def check():
        records = call("episode_session.read_session.ReadSession", {"episode_id": episode_id})
        authors = [record for record in records if record["kind"] == SessionKind.AUTHOR]
        if not authors or authors[-1]["action"] is None:
            return None
        return {"status": "written", "record": {name: authors[-1][name] for name in ("id", "action")}}
    return _waited(check, interval, timeout) or {"status": "timeout"}


def _text_arg(args: argparse.Namespace) -> str:
    """文を、--file のファイルか、--text の引数(- なら標準入力)から読む。"""
    if args.file is not None:
        return Path(args.file).read_text(encoding="utf-8")
    return sys.stdin.read() if args.text == "-" else args.text


def _answer(record: dict[str, Any]) -> dict[str, Any]:
    """返った一手。要求は語り部が書いたばかりなので返さない。"""
    return {"id": record["id"], "character": record["character"]["name"],
            **{name: record[name] for name in ("thought", "action", "speech", "aim")}}


def moves(episode_id: int, after: int) -> dict[str, Any]:
    """`after` より後の手番のうち、一手の入ったものと、まだ埋まっていない行の id。待たない。"""
    records = call("episode_session.read_session.ReadSession", {"episode_id": episode_id})
    turns = [record for record in records if record["kind"] == SessionKind.CHARACTER and record["id"] > after]
    return {"answers": [_answer(record) for record in turns if record["action"] is not None],
            "pending": [record["id"] for record in turns if record["action"] is None]}


def _out_name(args: argparse.Namespace) -> str:
    """書き出すファイルの名。人物役は何人も同時に動くので、コマンドと話・人物・行で分ける。"""
    parts = [args.command] + [f"{key[0]}{getattr(args, key)}" for key in ("episode", "character", "record", "after")
                              if getattr(args, key, None) is not None]
    if getattr(args, "time", None):
        parts.append("t" + "".join(char for char in args.time if char.isdigit()))
    return "-".join(parts)


def write_file(result: Any, name: str) -> dict[str, Any]:
    """結果の JSON をファイルに書き、そのパスと大きさを返す。"""
    text = json.dumps(result, ensure_ascii=False, indent=2)
    path = OUT_DIR / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"file": str(path), "chars": len(text), "lines": text.count("\n") + 1,
            "note": "Read(allow_large)で最後の行まで読む"}


def _turns_args(text: str) -> dict[str, Any]:
    """`add` の JSON。手番の配列か、語りと見聞きする人物を添えた `{"narration", "witness_ids", "turns"}`。"""
    value = json.loads(text)
    return {"turns": value} if isinstance(value, list) else value


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

    played = commands.add_parser("played", help="自分がもう動いた手番(要求と自分の一手)を読む(起こし直されたときに)")
    played.add_argument("--episode", type=int, required=True)
    played.add_argument("--character", type=int, required=True)

    turn = commands.add_parser("turn", help="語り部に知らされた番の行(見聞きしたことと要求)を読む。待たない")
    turn.add_argument("--episode", type=int, required=True)
    turn.add_argument("--character", type=int, required=True)
    turn.add_argument("--record", type=int, required=True, help="語り部が送ってきた行の id")

    answer = commands.add_parser("answer", help="自分の番の行に一手を入れる")
    answer.add_argument("--record", type=int, required=True)
    answer.add_argument("--action", required=True)
    answer.add_argument("--thought")
    answer.add_argument("--speech")
    answer.add_argument("--aim")

    appearance = commands.add_parser("appearance", help="初対面の相手から見て分かること(名前なし)を読む")
    appearance.add_argument("--character", type=int, required=True)
    appearance.add_argument("--time", required=True)

    knower_gaps = commands.add_parser(
        "knower-gaps", help="登場人物の来歴のうち、ほかの登場人物の名前が出るのに、その人物が知る相手に入っていない行を挙げる")
    knower_gaps.add_argument("--episode", type=int, required=True)

    stage = commands.add_parser("stage", help="語り部が読む材料(プロット・場所・登場人物の表層・知り合いの組)を読む")
    stage.add_argument("--episode", type=int, required=True)

    add = commands.add_parser("add", help="手番の要求の行を足す(JSON: narration・witness_ids と、turns の配列: character_id・time・request・witness_ids)")
    add.add_argument("--episode", type=int, required=True)
    add.add_argument("--turns", required=True, help="JSON のファイル。- なら標準入力から読む")

    add_ideas = commands.add_parser(
        "add-ideas", help="場面に出した新しい語をアイデアと照らし、当たらなければ候補として足す(JSON の配列: keyword・description・kind)")
    add_ideas.add_argument("--episode", type=int, required=True)
    add_ideas.add_argument("--ideas", required=True, help="JSON のファイル。- なら標準入力から読む")

    answers = commands.add_parser("moves", help="--after より後の手番の一手と、まだ埋まっていない行を読む。待たない")
    answers.add_argument("--episode", type=int, required=True)
    answers.add_argument("--after", type=int, default=0)

    read = commands.add_parser("read", help="セッションの行をすべて読む")
    read.add_argument("--episode", type=int, required=True)

    text = commands.add_parser("text", help="いま保存されている本文の全文を読む")
    text.add_argument("--episode", type=int, required=True)

    append = commands.add_parser("append", help="人物役の一手を起こした文を本文の終わりに書き足す(作者の番には断られる)")
    append.add_argument("--episode", type=int, required=True)
    appended = append.add_mutually_exclusive_group(required=True)
    appended.add_argument("--file", help="書き足す文のファイル")
    appended.add_argument("--text", help="書き足す文。- なら標準入力から読む")

    replace = commands.add_parser("replace", help="本文のうち old の箇所を new に置き換える(作者がプロットのように書いた所を起こし直す。作者の番には断られる)")
    replace.add_argument("--episode", type=int, required=True)
    replace.add_argument("--edit", required=True, help='JSON {"old": 置き換える文, "new": 置き換えた文} のファイル。- なら標準入力から読む')

    hand_over = commands.add_parser("hand-over", help="一巡を終え、作者に番を渡す(作者の行を足す)")
    hand_over.add_argument("--episode", type=int, required=True)
    hand_over.add_argument("--note", help="作者に渡す一言(画面の作者の行に出る)")
    hand_over.add_argument("--wait", action="store_true", help="渡したあと、作者が書くまで待ち、wait-author と同じ JSON を返す")

    author_wait = commands.add_parser("wait-author", help="作者が書く(written)まで待つ")
    author_wait.add_argument("--episode", type=int, required=True)

    author = commands.add_parser("author", help="作者がチャットで出した発言を作者の行に入れる(作者の番でなければ作者の行を挟む)")
    author.add_argument("--episode", type=int, required=True)
    said = author.add_mutually_exclusive_group(required=True)
    said.add_argument("--file", help="作者の発言のファイル")
    said.add_argument("--text", help="作者の発言。- なら標準入力から読む")

    clear = commands.add_parser("clear", help="話のセッションの行をすべて消す(手番を演じ直す前と、作者と書き終えたときに)")
    clear.add_argument("--episode", type=int, required=True)
    clear.add_argument("--from", dest="from_record", type=int, help="この行の id から後(この行を含む)だけを消す")

    # 作者の書くのを待つのは語り部だけ。Bash は前で 600 秒しか待たず、過ぎると裏へ回して待ちを拾えなくなるので、
    # その前に timeout を返して待ち直させる
    for waiting in (hand_over, author_wait):
        waiting.add_argument("--interval", type=float, default=1.0)
        waiting.add_argument("--timeout", type=float, default=540.0)

    args = parser.parse_args()
    configure_logging()
    # 待つあいだの呼び出しごとのログが、人物役・語り部の読む出力に積もって入力のトークンを食う
    logging.getLogger("httpx").setLevel(logging.WARNING)
    match args.command:
        case "knowledge":
            result = call("character.read_knowledge.ReadKnowledge", {"character_id": args.character, **_moment(args)})
        case "ideas":
            result = call("character.read_known_ideas.ReadKnownIdeas",
                          {"character_id": args.character, "words": args.word, **_moment(args)})
        case "played":
            result = call("episode_session.read_played_turns.ReadPlayedTurns",
                          {"episode_id": args.episode, "character_id": args.character})
        case "turn":
            result = read_turn(args.episode, args.character, args.record)
        case "answer":
            fields = {"thought": args.thought, "action": args.action, "speech": args.speech, "aim": args.aim}
            result = _answer(call("episode_session.answer_turn.AnswerTurn", {
                "record_id": args.record, "answer": {name: value for name, value in fields.items() if value is not None}}))
        case "appearance":
            result = call("character.read_appearance.ReadAppearance", {"character_id": args.character, "time": args.time})
        case "knower-gaps":
            result = call("episode_session.read_knower_gaps.ReadKnowerGaps", {"episode_id": args.episode})
        case "stage":
            result = call("episode_session.read_stage.ReadStage", {"episode_id": args.episode})
        case "add":
            text = sys.stdin.read() if args.turns == "-" else Path(args.turns).read_text(encoding="utf-8")
            result = [_row(record) for record in
                      call("episode_session.add_turns.AddTurns", {"episode_id": args.episode, **_turns_args(text)})]
        case "add-ideas":
            text = sys.stdin.read() if args.ideas == "-" else Path(args.ideas).read_text(encoding="utf-8")
            result = call("episode_session.add_ideas.AddIdeas", {"episode_id": args.episode, "ideas": json.loads(text)})
        case "moves":
            result = moves(args.episode, args.after)
        case "read":
            result = [_row(record) for record in call("episode_session.read_session.ReadSession", {"episode_id": args.episode})]
        case "text":
            [episode] = call("episode.read_episode_texts.ReadEpisodeTexts", {"episode_ids": [args.episode]})
            result = {"title": episode["title"], "main_text": episode["main_text"]}
        case "append":
            result = call("episode_session.append_text.AppendText", {"episode_id": args.episode, "text": _text_arg(args)})
        case "replace":
            text = sys.stdin.read() if args.edit == "-" else Path(args.edit).read_text(encoding="utf-8")
            result = call("episode_session.replace_text.ReplaceText", {"episode_id": args.episode, **json.loads(text)})
        case "hand-over":
            result = call("episode_session.hand_over.HandOver",
                          {"episode_id": args.episode} | ({} if args.note is None else {"request": args.note}))
            result = wait_author(args.episode, args.interval, args.timeout) if args.wait else _row(result)
        case "wait-author":
            result = wait_author(args.episode, args.interval, args.timeout)
        case "author":
            result = _row(call("episode_session.add_author_line.AddAuthorLine",
                               {"episode_id": args.episode, "text": _text_arg(args)}))
        case "clear":
            result = call("episode_session.clear_session.ClearSession", {"episode_id": args.episode} | (
                {} if args.from_record is None else {"from_record_id": args.from_record}))
        case _:
            parser.error(f"知らないコマンド: {args.command}")
    if args.command in FILE_COMMANDS:
        result = write_file(result, _out_name(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
