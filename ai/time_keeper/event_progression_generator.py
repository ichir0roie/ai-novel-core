#!/usr/bin/env python3
from __future__ import annotations

import random
from collections import defaultdict
from typing import Mapping

from sqlalchemy import select

from ai.instructions.event_writing import (
    CHARACTER_NOTE_LIMIT, CHARACTER_NOTE_SEPARATOR,
    CHARACTER_TEXT_UPDATE_INSTRUCTION, EVENT_AGE_INSTRUCTION, EVENT_DURATION_INSTRUCTION,
    EVENT_PROGRESSION_INSTRUCTION, EVENT_RECORD_INSTRUCTION,
    RECENT_EVENT_LIMIT,
)
from ai.instructions.naming import (
    PLACE_NAMING_INSTRUCTION, fill_name_placeholder,
)
from data_access_logic.query import (
    common_query, story_createion_query, world_createion_query,
)
from data_access_logic.query.base import (
    character_active_condition, location_active_condition,
)
from db.schema import (
    Character, CharacterPlace, ConfirmStatus, Event, EventCharacter,
    Location, Session, Stamp,
)
from ai.time_keeper._ai import AIClient
from ai.time_keeper import constants, event_summary
from ai.time_keeper._format import add_days, days_between, format_time
from randomizer.random_location_generator import build_location

_EVENT_TEXT_INSTRUCTION = f"""\
選ばれた出来事の候補(name と summary)を、当事者ごとの思考・感情・望み・恐れ・行動を土台にして記録に起こす。
候補の筋から外れない。
{EVENT_RECORD_INSTRUCTION}"""


_INVOLVEMENT_INSTRUCTION = """\
関わった人物・対象があれば、その id を渡した一覧の中からだけ選んで character_ids に入れる(複数可)。"""

_CHARACTER_MOVE_INSTRUCTION = """\
character_moves は、この出来事で居場所が変わった人物だけのリスト(旅立ち・移住・避難・帰還など)。
各要素は character_id(渡した「居合わせる人物」の id)と location_id(渡した「移動先の候補」の id)の二つ。
誰も動いていなければ空リストにする。"""

_LOCATION_CHANGE_INSTRUCTION = f"""\
この出来事が場所自身の改廃(消滅・新設)に及ぶときだけ、location_abolished / location_founded を埋める。
何も変わっていなければ location_abolished は false、location_founded は null のままにする。
location_founded の固有名詞は次の基準で名づける。
{PLACE_NAMING_INSTRUCTION}"""

_JUDGEMENT_KEYS = ("thought", "emotion", "wish", "fear", "action")

_JUDGEMENT_SYSTEM_PROMPT = f"""\
あなたは架空の世界観の中で、ある一人の人物、または人物以外の一つの対象(国・組織・集団・物)の立場に立って考える設定作家です。
渡す場所・直近の出来事・筋書き・居合わせる相手を踏まえ、「この当事者」のいまを、その kind・text・口調・方言・性格(traits。各軸は 無/低/並/高/必 の五段階)・立場・世界線への影響度から推測してください。
人物なら性格と人間関係から、人物以外なら方針と力の及ぶ範囲から。
{EVENT_AGE_INSTRUCTION}
他の当事者のことは決めない。この当事者自身のことだけを書く。
JSON で答えてください。キーは次の五つ。各1〜2文。
- thought: 思考。いまの状況をどう受け止め、何を考えているか。
- emotion: 感情。何に対して怒り・喜び・悲しみ・退屈・不安などを抱いているか。感情の名前を含める。
- wish: 望み。何を手に入れたい・何をしたいか。
- fear: 恐れ。何を失いたくない・何が起きてほしくないか。
- action: 行動。この時点で実際に何をするか。話す・動く・作る・出かける・黙るなど具体的な動作で。"""

_JUDGEMENT_SCHEMA = {
    "type": "object",
    "properties": {key: {"type": "string"} for key in _JUDGEMENT_KEYS},
    "required": list(_JUDGEMENT_KEYS),
    "additionalProperties": False,
}

_CANDIDATE_SYSTEM_PROMPT = f"""\
あなたは、ある場所に起こる出来事を列挙する作家です。
渡す場所・居合わせる人物・対象・当事者ごとの思考・感情・望み・恐れ・行動・直近の出来事・筋書きを踏まえ、
これらの行動が同じ場で重なった結果として、この時点で起こりうる出来事の候補を{constants.CANDIDATE_COUNT}件挙げてください。
日常の小さな、感情がぶつかる、偶発的な(事故・天候・病・思いがけない出会い)、居場所が変わる(旅立ち・帰還・避難)、
笑いや祝い、取り決めや対立が動くなど、種類の違うものを混ぜてください。
各候補は当事者の action と矛盾しない範囲で立てる。
{EVENT_AGE_INSTRUCTION}
{EVENT_PROGRESSION_INSTRUCTION}
JSON で答えてください。キーは candidates(候補のリスト。各要素は name(出来事の名前)と summary(何が起きて誰が関わるか。2〜3文)の二つ)だけ。"""

_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["name", "summary"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["candidates"],
    "additionalProperties": False,
}

_PLACE_SYSTEM_PROMPT = f"""\
あなたは架空の世界観の中で、ある場所に起きたことを記録する設定作家です。
その場所自身の情報、そこに居合わせる人物・対象の一覧、その場所の直近の出来事、当事者ごとの思考・感情・望み・恐れ・行動、そしてサイコロで選ばれた出来事の候補を渡すので、その候補をこの場所にこの時点で起きた出来事として1件、記録に起こしてください。
候補の name は event_name にそのまま使うか、整えてもよい。
{EVENT_AGE_INSTRUCTION}
{_INVOLVEMENT_INSTRUCTION}
{_CHARACTER_MOVE_INSTRUCTION}
{_LOCATION_CHANGE_INSTRUCTION}
JSON で答えてください。キーは次の八つだけ。
- event_name: 出来事の名前。
- event_text: 出来事の内容。書き方は後述の「event_text の書き方」に従う。
- character_ids: 関わった人物・対象の id のリスト。渡した「居合わせる人物・対象」の character_id からだけ選ぶ。
- character_moves: 居場所が変わった人物のリスト。各要素は character_id と location_id。
- character_updates: 関わった人物・対象のうち、この出来事でレコード自体が変わった者だけのリスト。各要素は character_id(対象の id)と text の二つ。text は後述の「character_updates の text の書き方」に従う。
- location_abolished: bool。この出来事でこの場所自体が消滅・放棄されたか。
- location_founded: この出来事でこの場所の配下に新しい場所が生まれたなら {{name, kind, text, environment}}。無ければ null。
- event_duration_days: {EVENT_DURATION_INSTRUCTION}

event_text の書き方:
{_EVENT_TEXT_INSTRUCTION}

character_updates の text の書き方:
{CHARACTER_TEXT_UPDATE_INSTRUCTION}"""

_LOCATION_FOUND_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "name": {"type": "string"},
        "kind": {"type": "string"},
        "text": {"type": "string"},
        "environment": {"type": "string"},
    },
    "required": ["name", "kind", "text", "environment"],
    "additionalProperties": False,
}

_PLACE_SCHEMA = {
    "type": "object",
    "properties": {
        "event_name": {"type": "string"},
        "event_text": {"type": "string"},
        "character_ids": {"type": "array", "items": {"type": "integer"}},
        "character_moves": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "integer"},
                    "location_id": {"type": "integer"},
                },
                "required": ["character_id", "location_id"],
                "additionalProperties": False,
            },
        },
        "character_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["character_id"],
                "additionalProperties": False,
            },
        },
        "location_abolished": {"type": "boolean"},
        "location_founded": _LOCATION_FOUND_SCHEMA,
        "event_duration_days": {
            "type": "integer",
            "minimum": constants.EVENT_DURATION_RANGE_DAYS[0],
            "maximum": constants.EVENT_DURATION_RANGE_DAYS[1],
        },
    },
    "required": [
        "event_name", "event_text", "character_ids",
        "character_moves",
        "character_updates",
        "location_abolished", "location_founded",
        "event_duration_days",
    ],
    "additionalProperties": False,
}


def _should_roll(time: Stamp) -> bool:
    return time.day == 1


def _place_roll_probability(session: Session, place_id: int, time: Stamp) -> float:
    last_event = session.scalars(
        common_query.events_of_place_select(place_id, until=time, limit=1)
    ).first()
    if last_event is None:
        return constants.PLACE_PROBABILITY
    months_since = days_between(last_event.time, time) / 30
    if months_since >= constants.PLACE_COOLDOWN_MONTHS:
        return constants.PLACE_PROBABILITY
    return constants.PLACE_PROBABILITY * constants.PLACE_PROBABILITY_COOLDOWN_FACTOR


def _append_note(record: Character, note: str) -> None:
    if not record.text:
        record.text = note
        return
    base, *notes = record.text.split(CHARACTER_NOTE_SEPARATOR)
    notes.append(note)
    notes = notes[-(CHARACTER_NOTE_LIMIT - 1):] if CHARACTER_NOTE_LIMIT > 1 else []
    record.text = CHARACTER_NOTE_SEPARATOR.join([base, *notes])


def _current_place_id(session: Session, character: Character, time: Stamp) -> int | None:
    place = session.scalars(
        common_query.character_place_select(character.id, time)).first()
    return place.location_id if place else None


def _group_by_place(session: Session, time: Stamp) -> dict[int, list[Character]]:
    grouped: dict[int, list[Character]] = defaultdict(list)

    busy_character_ids = set(session.scalars(
        world_createion_query.busy_character_ids_select(time)).all())

    active_place_ids = set(session.scalars(
        select(Location.id).where(location_active_condition(time))).all())

    characters = session.scalars(
        world_createion_query.alive_characters_select(time)
        .where(character_active_condition())).all()
    for character in characters:
        if character.id in busy_character_ids:
            continue
        place_id = _current_place_id(session, character, time)
        if place_id is None or place_id not in active_place_ids:
            continue
        grouped[place_id].append(character)

    return grouped


def _character_recent_event_names(
    session: Session, character_id: int, time: Stamp,
) -> list[str]:
    events = session.scalars(
        common_query.events_of_character_select(character_id, until=time, limit=RECENT_EVENT_LIMIT)
    ).all()
    return [e.name for e in events]


def age_at(character: Character, time: Stamp) -> int | None:
    if character.start is None:
        return None
    born = character.start
    return time.year - born.year - ((time.month, time.day) < (born.month, born.day))


def _relations(session: Session, character: Character, time: Stamp) -> list[str]:
    lines = []
    for relation in session.scalars(
            common_query.character_relations_at_select(character.id, time)
            .limit(constants.RELATION_LIMIT)).all():
        first = session.get(Character, relation.character_id_1)
        second = session.get(Character, relation.character_id_2)
        note = f"({relation.text})" if relation.text else ""
        lines.append(f"{first.name if first else '?'}から見た{second.name if second else '?'}: "
                     f"{relation.relation}{note}")
    return lines


def _story_recent_event_names(
    session: Session, top_location_id: int | None, place_id: int, time: Stamp,
) -> list[str]:
    """横(兄弟の場所)の出来事は含めない。作品の配下全体を渡すと、他の国の
    展開まで持ち込まれて場所ごとの差が消えるため(2026-09 に観測)。
    """
    place_ids = []
    for step in reversed(common_query.place_path(session, place_id)):
        place_ids.append(step["id"])
        if step["id"] == top_location_id:
            break
    events = session.scalars(
        common_query.events_in_locations_select(
            place_ids, until=time, limit=RECENT_EVENT_LIMIT)
    ).all()
    return [e.name for e in events]


def _later_events(
    session: Session, place_id: int | None, characters: list[Character], time: Stamp, ai: AIClient,
) -> list[dict]:
    """本文は写させないよう要約で渡す。"""
    events = session.scalars(common_query.events_after_select(
        place_id, [c.id for c in characters], time, limit=constants.LATER_EVENT_LIMIT)).all()
    rows = []
    for event in events:
        row = {"name": event.name, "start": str(event.start or event.time),
               "end": str(event.end) if event.end else None}
        summary = event_summary.summarize(session, event, ai)
        rows.append({**row, "summary": summary} if summary else row)
    return rows


def _think_participants(
    situation: str, characters_payload: list[dict], ai: AIClient,
) -> list[dict]:
    judgements: list[dict] = []
    for payload in characters_payload:
        prompt = f"""\
この当事者({payload['kind']}): {payload}
{situation}この当事者のいまの思考・感情・望み・恐れ・行動を推測してください。"""
        decided = ai.try_generate_json(
            prompt, _JUDGEMENT_SCHEMA, system=_JUDGEMENT_SYSTEM_PROMPT)
        fields = {key: (decided.get(key) or "").strip() for key in _JUDGEMENT_KEYS}
        if not fields["action"]:
            continue
        judgements.append({"character_id": payload["character_id"], "name": payload["name"], **fields})
    return judgements


def _roll_candidate(
    rng: random.Random, situation: str, judgements: list[dict], ai: AIClient,
    seeds: list[str] | None = None,
) -> dict | None:
    seed_lines = (
        f"出来事の種(時代・場所を抜いた、別の物語から取ったアイデア): {seeds}\n"
        "候補は、この種のどれかをこの場所・この時点・この当事者に合わせて具体化したものか、"
        "直前・直近の出来事から連想したものにする。\n"
    ) if seeds else ""
    prompt = f"""\
当事者ごとの思考・感情・望み・恐れ・行動: {judgements or '(無し)'}
{situation}{seed_lines}この場所にこの時点で起こりうる出来事の候補を{constants.CANDIDATE_COUNT}件挙げてください。"""
    decided = ai.try_generate_json(
        prompt, _CANDIDATE_SCHEMA, system=_CANDIDATE_SYSTEM_PROMPT)
    candidates = [
        c for c in (decided.get("candidates") or [])
        if isinstance(c, dict) and c.get("name")
    ]
    if not candidates:
        return None
    chosen = rng.choice(candidates)
    return {"name": chosen["name"], "summary": chosen.get("summary") or "",
            "rolled": f"{candidates.index(chosen) + 1}/{len(candidates)}"}


def _move_destinations(
    session: Session, place_id: int, time: Stamp,
) -> list[dict]:
    root_id = common_query.place_up(session, place_id, constants.REACH_LEVELS)
    nearby_ids = set(common_query.descendant_place_ids(session, root_id))
    nearby_ids -= {place_id, root_id}
    places = session.scalars(
        world_createion_query.alive_locations_select(time)
        .where(Location.id.in_(nearby_ids), location_active_condition(time))
    ).all()
    return [{"location_id": p.id, "name": p.name, "kind": p.kind}
            for p in places[:constants.MOVE_DESTINATION_LIMIT]]


def _progress_place(
    session: Session, place_id: int,
    characters: list[Character], time: Stamp, rng: random.Random, ai: AIClient,
    *, focus: Character | None = None, note: str = "", seeds: list[str] | None = None,
    use_story: bool = True,
) -> Event | None:
    recent_events = session.scalars(
        common_query.events_of_place_select(place_id, until=time, limit=RECENT_EVENT_LIMIT)
    ).all()
    place = session.get(Location, place_id)
    stories = story_createion_query.load_location_story(session, place_id, time) if use_story else []
    story_text = story_createion_query.join_story_text(stories)
    story_recent_events = (
        _story_recent_event_names(session, stories[0].place_id, place_id, time)
        if stories else []
    )
    characters_payload = [
        {"character_id": c.id, "kind": c.kind, "name": c.name, "age": age_at(c, time),
         "family_name": parameters["family_name"],
         "tone": parameters["tone"], "dialect": parameters["dialect"], "text": c.text,
         "traits": {column: parameters[column] for column in constants.TRAIT_COLUMNS},
         "relations": _relations(session, c, time),
         "recent_events": _character_recent_event_names(session, c.id, time)}
        for c in characters[:20]
        for parameters in (c.parameters_at(time),)
    ]
    destinations = _move_destinations(session, place_id, time)
    later_events = _later_events(session, place_id, characters, time, ai)
    later_lines = (
        "この時点より後に既に決まっている出来事(これと矛盾させず、先回りして起こさない): "
        f"{later_events}\n"
    ) if later_events else ""
    story_lines = f"""\
進めたい筋書き(上位の場所のものから順につなげた作品の本文):
{story_text or '(指定なし)'}
筋書きに関わる直近の出来事(この場所とその上位の場所で直近使われた出来事の名前): {story_recent_events or '(無し)'}
""" if use_story else ""

    situation = f"""\
場所id: {place_id}
場所の情報: {(place.name, place.kind, place.text) if place else None}
居合わせる人物・対象(kind が「人物」以外なら国・組織・集団・物。age は人物なら歳、それ以外は成立からの年数。relations はその時点で続いている相関。recent_events はその者自身が場所を問わず関わった直近の出来事): {characters_payload}
直近の出来事(名前): {[e.name for e in recent_events]}
{later_lines}{story_lines}{note}現在の時刻: {time}
"""
    judgements = _think_participants(situation, characters_payload, ai)
    candidate = _roll_candidate(rng, situation, judgements, ai, seeds)
    if candidate is None:
        return None

    candidate_summary = {"name": candidate["name"], "summary": candidate["summary"]}
    hints = "\n".join(hint for hint in (
        "進めたい筋書きがあるなら、そこへ向かう一歩になる出来事を優先する。" if stories else "",
        "居合わせる人物・対象の text に筋書きが書かれていれば、その者個人について進めたい筋書きとして扱い、そこへ向かう一歩になる出来事を優先する。"
        if use_story else "",
    ) if hint)
    prompt = f"""\
{situation}移動先の候補(character_moves の location_id はここからだけ選ぶ): {destinations or '(無し)'}
当事者ごとの思考・感情・望み・恐れ・行動(先に推測したもの): {judgements or '(無し)'}
サイコロで選ばれた出来事の候補: {candidate_summary}
この候補を、この場所にこの時点で起きた出来事として記録してください。
event_text 内では番号ではなく名前で書く。
{hints}"""
    decided = ai.try_generate_json(prompt, _PLACE_SCHEMA, system=_PLACE_SYSTEM_PROMPT)

    if not decided.get("event_name"):
        return None

    event_name = decided["event_name"]
    event_text = decided.get("event_text") or ""

    character_ids = {c.id: c for c in characters}

    def _valid_ids(raw, pool: Mapping[int, object]) -> list[int]:
        result: list[int] = []
        for value in raw or []:
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
            if value in pool and value not in result:
                result.append(value)
        return result

    involved_character_ids = _valid_ids(decided.get("character_ids"), character_ids)
    if focus is not None and focus.id not in involved_character_ids:
        involved_character_ids.insert(0, focus.id)

    destination_names = {d["location_id"]: d["name"] for d in destinations}
    move_notes = []
    for move in decided.get("character_moves") or []:
        if not isinstance(move, dict):
            continue
        try:
            character_id = int(move.get("character_id") or 0)
            location_id = int(move.get("location_id") or 0)
        except (TypeError, ValueError):
            continue
        character = character_ids.get(character_id)
        if character is None or location_id not in destination_names:
            continue
        for current in session.scalars(
                common_query.character_place_select(character_id, time)).all():
            current.end = time
        session.add(CharacterPlace(
            character_id=character_id, location_id=location_id,
            start=time, end=character.end))
        if character_id not in involved_character_ids:
            involved_character_ids.append(character_id)
        move_notes.append(f"{character.name} → {destination_names[location_id]}")

    raw_duration = decided.get("event_duration_days")
    try:
        duration_days = (int(raw_duration) if raw_duration is not None
                         else constants.DEFAULT_EVENT_DURATION_DAYS)
    except (TypeError, ValueError):
        duration_days = constants.DEFAULT_EVENT_DURATION_DAYS
    duration_days = min(max(duration_days, constants.EVENT_DURATION_RANGE_DAYS[0]),
                        constants.EVENT_DURATION_RANGE_DAYS[1])
    end = add_days(time, duration_days)

    record = Event(
        name=event_name,
        text=event_text,
        time=time,
        location_id=place_id,
        start=time,
        end=end,
        confirmed=ConfirmStatus.PENDING,
    )
    record.event_characters = [
        EventCharacter(character_id=cid) for cid in involved_character_ids
    ]
    session.add(record)

    update_notes = []
    for update in decided.get("character_updates") or []:
        if not isinstance(update, dict):
            continue
        try:
            character_id = int(update.get("character_id") or 0)
        except (TypeError, ValueError):
            continue
        character = character_ids.get(character_id)
        if character is None:
            continue
        applied = []
        if update.get("text"):
            note = fill_name_placeholder(update["text"], character.name or "")
            _append_note(character, note)
            applied.append(f"text+={note}")
        if applied:
            update_notes.append(f"{character.name}: {', '.join(applied)}")

    location_notes = []
    if decided.get("location_abolished") and place is not None and place.end is None:
        place.end = time
        location_notes.append(f"{place.name}(id={place_id}): 消滅")

    founded = decided.get("location_founded")
    if isinstance(founded, dict) and founded.get("name"):
        draft = build_location(
            parent_id=place_id,
            name=founded.get("name"),
            kind=founded.get("kind") or "集落",
            text=founded.get("text") or "",
            environment=founded.get("environment") or (place.environment if place else None),
            start=time,
            active_random_generation=place.active_random_generation if place else False,
        )
        new_location = Location(**draft)
        session.add(new_location)
        session.flush()
        location_notes.append(f"{new_location.name}(id={new_location.id}): 新設")

    session.commit()
    when = format_time(time)
    involved_names = [
        name for name in (character_ids[cid].name for cid in involved_character_ids) if name
    ]
    print(f"[time_keepr/event] {when} 場所id={place_id}: "
          f"{record.name} {record.text}"
          f" / 継続: {duration_days}日({when}〜{format_time(end)})"
          + (f" / 関わった: {', '.join(involved_names)}" if involved_names else "")
          + f" / 候補 {candidate['rolled']}: {candidate['name']}"
          + (f" / 移動: {'; '.join(move_notes)}" if move_notes else "")
          + (f" / 人物・対象更新: {'; '.join(update_notes)}" if update_notes else "")
          + (f" / 場所: {'; '.join(location_notes)}" if location_notes else ""))
    return record


def generate_random(session: Session, time: Stamp, ai: AIClient) -> list[Event]:
    if not _should_roll(time):
        return []

    seed = random.randrange(10 ** 9)
    rng = random.Random(seed)
    created: list[Event] = []

    grouped = _group_by_place(session, time)
    total_places = len(grouped)
    for i, (place_id, characters) in enumerate(grouped.items(), start=1):
        probability = _place_roll_probability(session, place_id, time)
        print(f"[time_keepr/event] 場所 {i}/{total_places} id={place_id}: "
              f"人物・対象{len(characters)}件 / ロール確率={probability:.2f}")
        if rng.random() < probability:
            event = _progress_place(session, place_id, characters, time, rng, ai)
            if event is not None:
                created.append(event)

    return created
