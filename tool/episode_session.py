#!/usr/bin/env python3
"""話のセッション(語り部と人物役の手番)を、手元でも web のセッションでも同じコマンドで扱う。

手番の行は db に置かず、手元のファイル(`data_access_logic/episode_session/store.py`)に持つ。掛け合いの前に読む材料
(knowledge・stage)・語を引く ideas・本文は、手元は入口を直に回し、web のセッション(`CLAUDE_CODE_REMOTE=true`)は API の入口を呼ぶ。
人物役は表を見張らない。語り部が番の行の id を人物役に送り、人物役はその行だけを読んで一手を入れる。
人物役がはじめに読む材料(knowledge・played)は標準出力に出さずファイルに書き、そのパスを出す(Read で最後まで読む)。

    人物役: knowledge / style / ideas / played / turn / answer
    語り部: knower-gaps / stage(登場人物と知り合いの組を手番のファイルに写す)/ appearance / add / wait / add-ideas / moves / read
    作者と代わる代わる書く語り部: text / append / replace
    演じ直す前・掛け合いを終えたとき: clear(--from で、その行から後だけ)

    .venv/bin/python -m tool.episode_session turn --episode 102 --character 1 --record 1290
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from data_access_logic.episode_session.store import ANSWER_FIELDS, Record, SessionStore
from data_access_logic.logs import configure_logging


# 長い Bash の結果は Claude Code が頭だけを見せてファイルに逃がし、人物役は逃がされた先を読み落としたまま演じた
# (知り合いを知らない人として返した)。人物の材料は数万字になるので、いつもファイルに書いて Read で読ませる
FILE_COMMANDS = ("knowledge", "played")
OUT_DIR = Path(__file__).resolve().parent.parent / ".cache" / "episode_session"
_WAIT_INTERVAL_SECONDS = 2


def call(entrance_id: str, args: dict[str, Any]) -> Any:
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        from web_session.transport import run_entrance
        return run_entrance(entrance_id, args)
    from gui.api import interface
    return interface.call(interface.db_entrance_class(entrance_id), args)


def read_turn(store: SessionStore, character_id: int, record_id: int) -> dict[str, Any]:
    """語り部に番を知らされた人物役が、その行(見聞きしたことと要求)を読む。待たない。
    知らされた行がまだ番でない(前の手番が埋まっていない)か、別の行が番なら、そのことを返す。"""
    state = store.turn(character_id)
    if state["status"] == "turn" and state["record"]["id"] != record_id:
        return {"status": "other", "record_id": state["record"]["id"]}
    return state


def _name(record: Record, cast: dict[int, str]) -> str | None:
    return None if record.character_id is None else cast.get(record.character_id)


def _row(record: Record, cast: dict[int, str]) -> dict[str, Any]:
    """語り部の読む行。人物は名前だけにする。"""
    row = asdict(record)
    del row["character_id"]
    return {"id": row.pop("id"), "kind": row.pop("kind"), "character": _name(record, cast), **row}


def _answer(record: Record, cast: dict[int, str]) -> dict[str, Any]:
    """返った一手。要求は語り部が書いたばかりなので返さない。"""
    return {"id": record.id, "character": _name(record, cast), **{name: getattr(record, name) for name in ANSWER_FIELDS}}


def moves(store: SessionStore, after: int) -> dict[str, Any]:
    """`after` より後の手番のうち、一手の入ったものと、まだ埋まっていない行の id。待たない。"""
    session = store.load()
    turns = [record for record in session.records if record.character_id is not None and record.id > after]
    return {"answers": [_answer(record, session.cast) for record in turns if record.action is not None],
            "pending": [record.id for record in turns if record.action is None]}


def wait(store: SessionStore, record_ids: list[int], timeout_seconds: int) -> dict[str, Any]:
    """`record_ids` の手番に一手が入るまで待つ。一手そのものは返さない(語り部は人物役の返り `終わった <id>: …` で読み、
    同じ一手を二度読まない)。待ちきれなければ、まだ埋まっていない行の id を返す。"""
    deadline = time.monotonic() + timeout_seconds
    while True:
        records = {record.id: record for record in store.load().records}
        unknown = [record_id for record_id in record_ids if record_id not in records]
        if unknown:
            raise ValueError(f"手番のファイルに無い行: {unknown}")
        pending = [record_id for record_id in record_ids if records[record_id].action is None]
        if not pending:
            return {"filled": record_ids}
        if time.monotonic() >= deadline:
            return {"filled": [record_id for record_id in record_ids if record_id not in pending], "pending": pending}
        time.sleep(_WAIT_INTERVAL_SECONDS)


def stage(store: SessionStore) -> Any:
    """語り部の材料を db から読み、登場人物と知り合いの組を手番のファイルに写す(行は残す)。"""
    result = call("episode_session.read_stage.ReadStage", {"episode_id": store.episode_id})
    store.set_stage({member["人物id"]: member["名前"] for member in result["登場人物"]},
                    [tuple(relation["人物id"]) for relation in result["知り合い"]])
    return result


def _knowing(episode_id: int | None, character_id: int, time: str | None) -> dict[str, Any]:
    """人物が知ることを読む話・時刻。話のときは、その人物の一番新しい手番の時刻(無ければ話の時刻)で読む。"""
    if episode_id is None:
        return {"time": time}
    actor_time = SessionStore(episode_id).actor_time(character_id)
    return {"episode_id": episode_id} | ({} if actor_time is None else {"time": actor_time})


def _text_arg(args: argparse.Namespace) -> str:
    """文を、--file のファイルか、--text の引数(- なら標準入力)から読む。"""
    if args.file is not None:
        return Path(args.file).read_text(encoding="utf-8")
    return sys.stdin.read() if args.text == "-" else args.text


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

    commands.add_parser("style", help="人物役の書き方(db の全体の行と人物役の行)を読む。一手・返事はこの書き方で書く")

    played = commands.add_parser("played", help="自分がもう動いた手番(要求と自分の一手)を読む(起こし直されたときに)")
    played.add_argument("--episode", type=int, required=True)
    played.add_argument("--character", type=int, required=True)

    turn = commands.add_parser("turn", help="語り部に知らされた番の行(見聞きしたことと要求)を読む。待たない")
    turn.add_argument("--episode", type=int, required=True)
    turn.add_argument("--character", type=int, required=True)
    turn.add_argument("--record", type=int, required=True, help="語り部が送ってきた行の id")

    answer = commands.add_parser("answer", help="自分の番の行に一手を入れる")
    answer.add_argument("--episode", type=int, required=True)
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

    stage_command = commands.add_parser(
        "stage", help="語り部が読む材料(プロット・場所・登場人物の表層・知り合いの組)を読み、登場人物と知り合いの組を手番のファイルに写す")
    stage_command.add_argument("--episode", type=int, required=True)

    add = commands.add_parser("add", help="手番の要求の行を足す(JSON: narration・witness_ids・simultaneous・time と、turns の配列: character_id・time・request・witness_ids)")
    add.add_argument("--episode", type=int, required=True)
    add.add_argument("--turns", required=True, help="JSON のファイル。- なら標準入力から読む")

    add_ideas = commands.add_parser(
        "add-ideas", help="場面に出した新しい語をアイデアと照らし、当たらなければ候補として足す(JSON の配列: keyword・description・kind)")
    add_ideas.add_argument("--episode", type=int, required=True)
    add_ideas.add_argument("--ideas", required=True, help="JSON のファイル。- なら標準入力から読む")

    waiting = commands.add_parser(
        "wait", help="番を送った手番の行に一手が入るまで待つ。一手は出さない(人物役の返りで読む)")
    waiting.add_argument("--episode", type=int, required=True)
    waiting.add_argument("--record", type=int, action="append", required=True,
                         help="待つ行の id。組の手番(simultaneous)なら --record を重ねる")
    waiting.add_argument("--timeout", type=int, default=600, help="待つ秒数の上限")

    answers = commands.add_parser("moves", help="--after より後の手番の一手と、まだ埋まっていない行を読む。待たない")
    answers.add_argument("--episode", type=int, required=True)
    answers.add_argument("--after", type=int, default=0)

    read = commands.add_parser("read", help="セッションの行をすべて読む")
    read.add_argument("--episode", type=int, required=True)

    text = commands.add_parser("text", help="いま保存されている本文の全文を読む")
    text.add_argument("--episode", type=int, required=True)

    append = commands.add_parser("append", help="人物役の一手を起こした文を本文の終わりに書き足す")
    append.add_argument("--episode", type=int, required=True)
    appended = append.add_mutually_exclusive_group(required=True)
    appended.add_argument("--file", help="書き足す文のファイル")
    appended.add_argument("--text", help="書き足す文。- なら標準入力から読む")

    replace = commands.add_parser("replace", help="本文のうち old の箇所を new に置き換える(作者がプロットのように書いた所を起こし直す)")
    replace.add_argument("--episode", type=int, required=True)
    replace.add_argument("--edit", required=True, help='JSON {"old": 置き換える文, "new": 置き換えた文} のファイル。- なら標準入力から読む')

    clear = commands.add_parser("clear", help="話のセッションの行をすべて消す(手番を演じ直す前と、掛け合いを終えたときに)")
    clear.add_argument("--episode", type=int, required=True)
    clear.add_argument("--from", dest="from_record", type=int, help="この行の id から後(この行を含む)だけを消す")

    args = parser.parse_args()
    configure_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        result = run(args)
    except ValueError as error:
        # 手番のファイルの断り(番でない・知り合いでないなど)は、語り部・人物役が読んで直せるよう一行で返す
        sys.exit(f"error: {error}")
    if args.command in FILE_COMMANDS:
        result = write_file(result, _out_name(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run(args: argparse.Namespace) -> Any:
    match args.command:
        case "knowledge":
            return call("character.read_knowledge.ReadKnowledge",
                        {"character_id": args.character, **_knowing(args.episode, args.character, args.time)})
        case "style":
            # `db.schema` は import すると db を決めるので(web のセッションは db に繋がない)、範囲の値をそのまま渡す
            return call("style_preference.read_writing_style.ReadWritingStyle", {"writing_style": {"scope": "人物役"}})
        case "ideas":
            return call("character.read_known_ideas.ReadKnownIdeas", {
                "character_id": args.character, "words": args.word, **_knowing(args.episode, args.character, args.time)})
        case "played":
            return SessionStore(args.episode).played(args.character)
        case "turn":
            return read_turn(SessionStore(args.episode), args.character, args.record)
        case "answer":
            store = SessionStore(args.episode)
            record = store.answer(args.record, {"thought": args.thought, "action": args.action, "speech": args.speech,
                                                "aim": args.aim})
            return _answer(record, store.load().cast)
        case "appearance":
            return call("character.read_appearance.ReadAppearance", {"character_id": args.character, "time": args.time})
        case "knower-gaps":
            return call("episode_session.read_knower_gaps.ReadKnowerGaps", {"episode_id": args.episode})
        case "stage":
            return stage(SessionStore(args.episode))
        case "add":
            store = SessionStore(args.episode)
            text = sys.stdin.read() if args.turns == "-" else Path(args.turns).read_text(encoding="utf-8")
            added = store.add(json.loads(text))
            cast = store.load().cast
            return [_row(record, cast) for record in added]
        case "add-ideas":
            text = sys.stdin.read() if args.ideas == "-" else Path(args.ideas).read_text(encoding="utf-8")
            return call("episode_session.add_ideas.AddIdeas", {"episode_id": args.episode, "ideas": json.loads(text)})
        case "wait":
            return wait(SessionStore(args.episode), args.record, args.timeout)
        case "moves":
            return moves(SessionStore(args.episode), args.after)
        case "read":
            session = SessionStore(args.episode).load()
            return [_row(record, session.cast) for record in session.records]
        case "text":
            [episode] = call("episode.read_episode_texts.ReadEpisodeTexts", {"episode_ids": [args.episode]})
            return {"title": episode["title"], "main_text": episode["main_text"]}
        case "append":
            return call("episode_session.append_text.AppendText", {"episode_id": args.episode, "text": _text_arg(args)})
        case "replace":
            text = sys.stdin.read() if args.edit == "-" else Path(args.edit).read_text(encoding="utf-8")
            return call("episode_session.replace_text.ReplaceText", {"episode_id": args.episode, **json.loads(text)})
        case "clear":
            return {"episode_id": args.episode, "deleted": SessionStore(args.episode).clear(args.from_record)}
    raise ValueError(f"知らないコマンド: {args.command}")


if __name__ == "__main__":
    main()
