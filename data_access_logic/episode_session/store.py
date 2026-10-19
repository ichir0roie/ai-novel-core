"""話のセッション(語り部と人物役の手番)の行を、db でなく手元のファイルに持つ。

掛け合いのあいだ手番を足す・読む・一手を入れるたびに API(Lambda・db)を往復すると、一手ごとに数秒かかった。
行は掛け合いのあいだだけ要るので、語り部と人物役が同じ機械で読み書きする `.cache` のファイルに置き、db には残さない。
掛け合いの前に読む材料(登場人物・知り合いの組)は、語り部が `stage` で db から読んだときに写しておく。

手番は id の順に回る。行動の入っていない一番古い人物の行が、いま動く番。語りの行は手番に数えない。
同時に動く手番(`simultaneous`)は、すぐ前の手番と組になり、組のまだ動いていない行すべてに一度に番が開く。
人物役は自分の番に、前の自分の番から後の、自分が見聞きする語りとほかの人物の一手を、要求といっしょに受け取る。
同じ組のほかの人物の一手は、同時に動いたので受け取らない(次の自分の番で受け取る)。

行のファイルは語り部だけが書き、一手はその行の人物役だけが行ごとのファイルに書く。同時に動く人物役が一つのファイルを
書き合わないので、鍵が要らない。
一手ごとに起こすコマンドなので、pydantic・sqlalchemy を読み込まない(読み込むだけで一回に 0.3〜0.5 秒かかる)。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2] / ".cache" / "episode_session"

CHARACTER = "人物"
NARRATION = "語り"

ANSWER_FIELDS = ("thought", "action", "speech", "aim")
TURN_KEYS = {"character_id", "time", "request", "witness_ids"}
ADD_KEYS = {"narration", "witness_ids", "simultaneous", "time", "turns"}


@dataclass
class Record:
    id: int
    kind: str
    time: str | None
    witnesses: list[int]
    request: str
    # 人物の行だけが持つ
    character_id: int | None = None
    # 前の手番と同時に動く手番
    simultaneous: bool = False
    thought: str | None = None
    action: str | None = None
    speech: str | None = None
    aim: str | None = None


@dataclass
class SessionState:
    episode_id: int
    # 登場人物の id と名前。`stage` で写す
    cast: dict[int, str] = field(default_factory=dict)
    # 話の時刻に知り合いの二人の組
    acquaintances: list[list[int]] = field(default_factory=list)
    # 消した行の id を使い直さない(止めた人物役が古い行の id に一手を入れないように)
    next_id: int = 1
    records: list[Record] = field(default_factory=list)


class SessionStore:
    def __init__(self, episode_id: int):
        self.episode_id = episode_id
        self.dir = ROOT / f"e{episode_id}"

    @property
    def _session_path(self) -> Path:
        return self.dir / "session.json"

    def _answer_path(self, record_id: int) -> Path:
        return self.dir / "answers" / f"{record_id}.json"

    def load(self) -> SessionState:
        """行と、人物役の入れた一手を合わせて読む。"""
        if not self._session_path.exists():
            return SessionState(episode_id=self.episode_id)
        value = json.loads(self._session_path.read_text(encoding="utf-8"))
        session = SessionState(episode_id=value["episode_id"], cast={int(key): name for key, name in value["cast"].items()},
                               acquaintances=value["acquaintances"], next_id=value["next_id"],
                               records=[Record(**record) for record in value["records"]])
        for record in session.records:
            path = self._answer_path(record.id)
            if record.kind == CHARACTER and path.exists():
                for name, answered in json.loads(path.read_text(encoding="utf-8")).items():
                    setattr(record, name, answered)
        return session

    def _save(self, session: SessionState) -> None:
        # 一手は行ごとのファイルにあるので、行のファイルには書かない
        records = [{**asdict(record), **dict.fromkeys(ANSWER_FIELDS)} for record in session.records]
        _write(self._session_path, {**asdict(session), "records": records})

    def set_stage(self, cast: dict[int, str], acquaintances: list[tuple[int, int]]) -> None:
        """語り部が db から読んだ登場人物と知り合いの組を写す。行はそのまま残す。"""
        session = self.load()
        session.cast = cast
        session.acquaintances = [sorted(pair) for pair in acquaintances]
        self._save(session)

    def add(self, value: dict[str, Any] | list[dict[str, Any]]) -> list[Record]:
        """語り部が、手番の要求の行を並べた順に足す(`tool.episode_session add` の JSON)。

        `narration` を渡すと、その場の何人もに見える・聞こえる状況を語りの行として手番の前に一つだけ足し、
        `witness_ids` の人物それぞれの次の番で届ける。手番の人物の一手も、見聞きする人物(手番の `witness_ids`、
        渡さなければ `witness_ids`)の次の番で届く。一手には名前が付くので、届けるのは知り合いにだけ。
        手番にも全体にも `witness_ids` を渡さなければ断る(渡し忘れると、一手が誰にも届かないまま進む)。誰にも見せないなら [] を渡す。
        語りの行の時刻は `time`、渡さなければ一つ目の手番の時刻。手番を足さずに語りだけを足すときは `time` が要る。
        """
        value = {"turns": value} if isinstance(value, list) else value
        _check_keys(value, ADD_KEYS, "add")
        turns = value.get("turns", [])
        for turn in turns:
            _check_keys(turn, TURN_KEYS, "turns の手番")
        narration = value.get("narration")
        witness_ids = value.get("witness_ids")
        time = value.get("time")
        session = self.load()
        if not session.cast:
            raise ValueError(f"話 id={self.episode_id} の材料を読んでいない。先に stage --episode {self.episode_id} を打つ")
        if narration is not None and not narration.strip():
            raise ValueError("narration が空")
        if not turns and narration is None:
            raise ValueError("turns か narration のどちらかが要る")
        if narration is not None and not witness_ids:
            raise ValueError("narration には、見聞きする人物(witness_ids)が要る")
        if narration is not None and not turns and time is None:
            raise ValueError("手番を足さずに語りだけを足すときは、語りの時刻(time)が要る")
        for turn in turns:
            if "character_id" not in turn:
                raise ValueError("turns の手番に、動く人物(character_id)が無い")
            if not turn.get("request", "").strip():
                raise ValueError(f"人物 id={turn.get('character_id')} の手番に、要求(request)が無い")
            if turn["character_id"] not in session.cast:
                raise ValueError(f"人物 id={turn['character_id']} は話 id={self.episode_id} の登場人物でない")
            if turn.get("witness_ids") is None and witness_ids is None:
                raise ValueError(
                    f"人物 id={turn['character_id']} の手番に、見聞きする人物(witness_ids)が無い。"
                    "その場で見える・聞こえる人物を渡す(誰にも見せないなら [] を渡す)")
        for character_id in {*(witness_ids or []), *(id_ for turn in turns for id_ in turn.get("witness_ids") or [])}:
            if character_id not in session.cast:
                raise ValueError(f"witness_ids の人物 id={character_id} は話 id={self.episode_id} の登場人物でない")
        known = {frozenset(pair) for pair in session.acquaintances}

        added = []
        if narration is not None:
            added.append(Record(id=0, kind=NARRATION, time=time or (turns[0].get("time") if turns else None),
                                witnesses=list(dict.fromkeys(witness_ids)), request=narration))
        for index, turn in enumerate(turns):
            character_id = turn["character_id"]
            witnesses = [id_ for id_ in dict.fromkeys(witness_ids if turn.get("witness_ids") is None else turn["witness_ids"])
                         if id_ != character_id]
            for witness_id in witnesses:
                if frozenset((character_id, witness_id)) not in known:
                    raise ValueError(
                        f"人物 id={witness_id} は人物 id={character_id} と知り合いでないので、名前の付いた一手を届けられない。"
                        "その人物の一手は、見て分かる言葉で語り(narration)か要求に書く")
            # 組の頭(一つ目)は前の手番と組にならない
            added.append(Record(id=0, kind=CHARACTER, character_id=character_id, time=turn.get("time"),
                                witnesses=witnesses, request=turn["request"],
                                simultaneous=bool(value.get("simultaneous")) and index > 0))
        for record in added:
            record.id = session.next_id
            session.next_id += 1
        session.records += added
        self._save(session)
        return added

    def turn(self, character_id: int) -> dict[str, Any]:
        """人物役が、いま自分の番か(turn。行・見聞きしたこと・要求)、待つか(waiting)を読む。"""
        session = self.load()
        own = next((record for record in session.records
                    if record.character_id == character_id and record.action is None), None)
        if own is None or own.id not in {record.id for record in _current_turns(session)}:
            return {"status": "waiting"}
        return {"status": "turn", "record": {"id": own.id, "seen": _seen_lines(session, own), "request": own.request}}

    def answer(self, record_id: int, answer: dict[str, str | None]) -> Record:
        """人物役が、自分の番の要求の行に一手(内心・行動・セリフ・狙い)を入れる。"""
        if not (answer.get("action") or "").strip():
            raise ValueError("action が空(動かないときも「なし」などと書く)")
        session = self.load()
        record = next((record for record in session.records if record.id == record_id), None)
        if record is None:
            raise ValueError(f"id={record_id} の行が話 id={self.episode_id} のセッションに無い")
        if record.kind != CHARACTER:
            raise ValueError(f"id={record_id} は人物の行でない")
        if record.action is not None:
            raise ValueError(f"id={record_id} にはもう行動が入っている")
        current = [row.id for row in _current_turns(session)]
        if record_id not in current:
            raise ValueError(f"id={record_id} はまだ番が来ていない(いまの番は id={current or None})")
        _write(self._answer_path(record_id), {name: answer.get(name) for name in ANSWER_FIELDS})
        for name in ANSWER_FIELDS:
            setattr(record, name, answer.get(name))
        return record

    def played(self, character_id: int) -> list[dict[str, Any]]:
        """人物役が、自分がもう動いた手番(見聞きしたこと・要求と自分の一手)を、手番の順に読む。
        手番をある行から演じ直すとき、起こし直した人物役がそれまでの場面を掴み直すために読む。"""
        session = self.load()
        return [{"id": record.id, "seen": _seen_lines(session, record), "request": record.request,
                 **{name: getattr(record, name) for name in ANSWER_FIELDS}}
                for record in session.records if record.character_id == character_id and record.action is not None]

    def text(self) -> str:
        """本文の材料で設定と照らす語を挙げる元(`episode/brief.py`)。行の要求・語りと一手を手番の順に並べたもの。"""
        return "\n".join(text for record in self.load().records
                         for text in (record.request, *(getattr(record, name) for name in ANSWER_FIELDS)) if text)

    def actor_time(self, character_id: int) -> str | None:
        """人物役がいる時刻。その人物の時刻の入った一番新しい手番の行の時刻(無ければ None。話の時刻で読む)。"""
        times = [record.time for record in self.load().records if record.character_id == character_id and record.time]
        return times[-1] if times else None

    def clear(self, from_record_id: int | None = None) -> int:
        """行を消す(`from_record_id` を渡すと、その行から後(その行を含む)だけ)。登場人物・知り合いの組は残す。
        前の行が残ると、人物役に前の場面が届くので、手番を演じ直す前に消す。"""
        session = self.load()
        if from_record_id is not None and all(record.id != from_record_id for record in session.records):
            raise ValueError(f"id={from_record_id} は話 id={self.episode_id} のセッションの行でない")
        dropped = [record for record in session.records if from_record_id is None or record.id >= from_record_id]
        session.records = [record for record in session.records if record not in dropped]
        for record in dropped:
            self._answer_path(record.id).unlink(missing_ok=True)
        if self._session_path.exists():
            self._save(session)
        return len(dropped)


def _check_keys(value: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{where} に知らない欄 {sorted(unknown)} がある。使えるのは {sorted(allowed)}")


def _write(path: Path, value: Any) -> None:
    """読む側が書きかけのファイルを読まないように、別のファイルに書いてから差し替える。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporary, path)


def _turn_rows(session: SessionState) -> list[Record]:
    return [record for record in session.records if record.kind == CHARACTER]


def _group_of(turns: list[Record], index: int) -> list[Record]:
    """`turns[index]` と同時に動く組(組でなければその行だけ)。"""
    start = index
    while start > 0 and turns[start].simultaneous:
        start -= 1
    end = index + 1
    while end < len(turns) and turns[end].simultaneous:
        end += 1
    return turns[start:end]


def _current_turns(session: SessionState) -> list[Record]:
    """いま番の開いている行。一番古いまだ動いていない行と、それと同じ組のまだ動いていない行。"""
    turns = _turn_rows(session)
    first = next((index for index, record in enumerate(turns) if record.action is None), None)
    if first is None:
        return []
    return [record for record in _group_of(turns, first) if record.action is None]


def _seen_lines(session: SessionState, record: Record) -> list[str]:
    """`record` の人物が、前の自分の番から `record` までに見聞きした語りと、ほかの人物の一手(内心・狙いは入れない)。
    手番は id の順に回るので、前の番より手前の行は、前の番で受け取っている。"""
    previous = max((row.id for row in session.records if row.character_id == record.character_id and row.id < record.id),
                   default=0)
    turns = _turn_rows(session)
    index = next(index for index, row in enumerate(turns) if row.id == record.id)
    together = {row.id for row in _group_of(turns, index)}
    lines = []
    for row in session.records:
        if not previous < row.id < record.id or row.id in together or record.character_id not in row.witnesses:
            continue
        if row.kind == NARRATION:
            lines.append(row.request)
        elif row.character_id is not None and row.character_id != record.character_id and row.action is not None:
            lines.append(f"{session.cast.get(row.character_id, f'人物 id={row.character_id}')}: {row.action}"
                         + (f"「{row.speech}」" if row.speech else ""))
    return lines
