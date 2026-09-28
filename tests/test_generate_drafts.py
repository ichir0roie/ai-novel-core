"""GUI の「AI で作成」。欄の値(下書き)を核に AI が全欄を組み立て直して行を足す入口(`Generate*`)。"""
import pytest

from ai.claude_code.interface.randomizer.generate_character import GenerateCharacter
from ai.claude_code.interface.randomizer.generate_event import GenerateEvent
from ai.claude_code.interface.story.generate_episode import GenerateEpisode
from ai.claude_code.interface.story.generate_frame import GenerateFrame
from ai.claude_code.interface.story.revise_episode import ReviseEpisode
from ai.time_keeper import episode_generator, episode_reviser, frame_generator, random_character_generator
from db.schema import (
    Character, CharacterPlace, ConfirmStatus, Episode, Event, EventCharacter, Location, Story,
)
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient

WHEN = Stamp(2100, 5, 1)


class _Ai(MockAIClient):
    """枠の時刻は読める形で、本文は決まった文で返す。"""

    def try_generate_json(self, prompt, schema, **kwargs):
        kwargs.pop("model", None)
        kwargs.pop("effort", None)
        decided = super().try_generate_json(prompt, schema, **kwargs)
        if schema is frame_generator._FRAME_SCHEMA:
            decided["start"] = "2100/06/01"
            decided["key"] = "## 場面\n1. 市場 / 甲 / 地図を買う\n## 狙い\n旅立ちの予感"
        if schema is episode_generator._SCHEMA:
            decided = {"title": "地図の市", "viewpoint": "甲", "text": "甲は地図を買った。"}
        if schema is episode_reviser._SCHEMA:
            decided = {"title": "", "text": "書き直した後の本文。"}
        return decided


def _prompts(ai, schema=None):
    return "\n".join(call["prompt"] for call in ai.calls if schema is None or call["schema"] is schema)


class _FailingBodyAi(_Ai):
    """話の枠は決めるが、本文を書く呼び出しだけ失敗させる(下書きが先に保存されているか確かめる用)。"""

    def try_generate_json(self, prompt, schema, **kwargs):
        if schema is episode_generator._SCHEMA:
            raise RuntimeError("本文の生成に失敗(テスト用)")
        return super().try_generate_json(prompt, schema, **kwargs)


class _FailingReviseAi(_Ai):
    """推敲の呼び出しだけ失敗させる(下書きが先に保存されているか確かめる用)。"""

    def try_generate_json(self, prompt, schema, **kwargs):
        if schema is episode_reviser._SCHEMA:
            raise RuntimeError("推敲に失敗(テスト用)")
        return super().try_generate_json(prompt, schema, **kwargs)


@pytest.fixture
def place(session):
    record = Location(name="港町", kind="町", text="港町の説明", start=Stamp(2000))
    session.add(record)
    session.flush()
    session.add(Story(name="港町の話", place_id=record.id, text="港町の筋書き", narration="三人称",
                      state="執筆中", start=Stamp(2090), end=Stamp(2300)))
    session.commit()
    return record


def _character(session, place, name, *, main_character=False, confirmed=ConfirmStatus.APPROVED) -> Character:
    record = Character(name=name, text=f"{name}の説明", start=Stamp(2080), main_character=main_character,
                       confirmed=confirmed)
    session.add(record)
    session.flush()
    session.add(CharacterPlace(character_id=record.id, location_id=place.id, start=Stamp(2080)))
    session.commit()
    return record


def _event(session, place, when) -> Event:
    record = Event(name="先の出来事", text="", time=when, start=when, end=when, location_id=place.id)
    session.add(record)
    session.commit()
    return record


# ---------------------------------------------------------------- 人物

def test_character_is_rebuilt_from_the_draft(session, place):
    ai = _Ai(seed=1)
    result = GenerateCharacter(
        {"name": "リオ", "text": "港で網を繕う", "place_id": place.id, "main_character": True,
         "start": "2080", "parameters": [{"sex": "女", "tone": "無口"}]},
        time=WHEN, seed=1, ai=ai).run()

    record = session.get(Character, result["id"])
    assert record.kind == "人物" and record.main_character is True
    assert record.start == Stamp(2080)  # 生年は下書きどおり(age = 20)
    assert record.parameters[0].sex == "女" and record.parameters[0].tone == "無口"
    assert session.query(CharacterPlace).filter_by(character_id=record.id, location_id=place.id).count() == 1
    content = _prompts(ai, random_character_generator._CONTENT_SCHEMA)
    assert "作者の指定" in content and "リオ" in content and "港で網を繕う" in content and "年齢(決まっている。age はこの値にする): 20" in content
    assert "作者が付けたい名: リオ" in _prompts(ai, random_character_generator._PERSON_NAME_SCHEMA)


def test_character_from_an_empty_draft_uses_the_latest_time(session, place):
    _event(session, place, WHEN)
    result = GenerateCharacter({}, seed=1, ai=_Ai(seed=1)).run()
    record = session.get(Character, result["id"])
    assert record.start is not None and record.start.year <= WHEN.year
    assert result["place_id"] is None


def test_character_needs_a_time_when_the_world_has_no_event(session):
    with pytest.raises(ValueError):
        GenerateCharacter({}, ai=_Ai(seed=1)).run()


def test_non_person_kind_in_the_draft_is_kept(session, place):
    result = GenerateCharacter({"kind": "商会", "place_id": place.id}, time=WHEN, seed=1, ai=_Ai(seed=1)).run()
    assert session.get(Character, result["id"]).kind == "商会"


def test_character_completes_the_missing_text_of_an_existing_record(session, place):
    record = _character(session, place, "リオ")
    record.text = ""
    session.commit()
    ai = _Ai(seed=1)

    result = GenerateCharacter({"id": record.id}, ai=ai).run()

    assert result["id"] == record.id
    session.refresh(record)
    assert record.text and record.name == "リオ"  # 名前は変わらない
    assert session.query(Character).count() == 1  # 新しい行を足さず、この行を直す
    content = _prompts(ai, random_character_generator._CONTENT_SCHEMA)
    assert "名前(決まっている): リオ" in content


def test_character_refuses_when_the_text_is_already_present(session, place):
    record = _character(session, place, "リオ")
    with pytest.raises(ValueError):
        GenerateCharacter({"id": record.id}, ai=_Ai(seed=1)).run()


# ---------------------------------------------------------------- 出来事

def test_event_is_raised_at_the_named_characters_place_with_the_draft_as_the_scene(session, place):
    first = _character(session, place, "甲", main_character=True)
    second = _character(session, place, "乙")
    ai = _Ai(seed=1)

    result = GenerateEvent(
        {"name": "市場の喧嘩", "text": "値切りから始まる", "time": str(WHEN),
         "character_ids": [first.id, second.id], "hidden": True}, seed=1, ai=ai).run()

    record = session.get(Event, result["id"])
    assert record.location_id == place.id and record.time == WHEN and record.hidden is True
    assert {row.character_id for row in session.query(EventCharacter).filter_by(event_id=record.id)} <= {first.id, second.id}
    assert "市場の喧嘩 / 値切りから始まる" in _prompts(ai)
    assert result["character_ids"] and set(result["character_ids"]) <= {first.id, second.id}


def test_event_from_an_empty_draft_uses_those_present_at_the_place(session, place):
    _character(session, place, "甲")
    _event(session, place, Stamp(2100, 4, 1))
    result = GenerateEvent({"location_id": place.id}, seed=1, ai=_Ai(seed=1)).run()
    record = session.get(Event, result["id"])
    assert record.location_id == place.id and record.time == Stamp(2100, 4, 1)


def test_event_needs_a_place_or_characters(session, place):
    _event(session, place, WHEN)
    with pytest.raises(ValueError):
        GenerateEvent({}, ai=_Ai(seed=1)).run()


def test_event_completes_the_missing_text_of_an_existing_record(session, place):
    first = _character(session, place, "甲")
    record = Event(name="市場の喧嘩", text="", time=WHEN, start=WHEN, end=WHEN, location_id=place.id)
    record.event_characters = [EventCharacter(character_id=first.id)]
    session.add(record)
    session.commit()
    ai = _Ai(seed=1)

    result = GenerateEvent({"id": record.id}, ai=ai).run()

    assert result["id"] == record.id
    session.refresh(record)
    assert record.text and record.name == "市場の喧嘩"  # 名前は変わらない
    assert result["character_ids"] == [first.id]
    assert session.query(Event).count() == 1  # 新しい行を足さず、この行を直す


def test_event_refuses_when_the_text_is_already_present(session, place):
    record = _event(session, place, WHEN)
    record.text = "すでにある本文"
    session.commit()
    with pytest.raises(ValueError):
        GenerateEvent({"id": record.id}, ai=_Ai(seed=1)).run()


# ---------------------------------------------------------------- 話の枠

def test_episode_frame_is_decided_without_a_body(session, place):
    story = session.query(Story).one()
    first = _character(session, place, "甲")
    ai = _Ai(seed=1)

    result = GenerateFrame({"story_id": story.id, "title": "港にて"}, character_ids=[first.id], ai=ai).run()

    record = session.get(Episode, result["id"])
    assert record.start == Stamp(2100, 6, 1) and "## 場面" in record.key and record.synced is False
    assert record.text == "" and result["text"] == "" and result["letters"] == 0
    prompt = _prompts(ai, frame_generator._FRAME_SCHEMA)
    assert "作者の指定 題: 港にて" in prompt and '"name": "甲"' in prompt


def test_episode_frame_keeps_the_drafted_time_and_can_redo_an_empty_frame(session, place):
    story = session.query(Story).one()
    slot = Episode(story_id=story.id, title="", key="", start=None)
    session.add(slot)
    session.commit()

    result = GenerateFrame({"id": slot.id, "start": "2101/01/02"}, ai=_Ai(seed=1)).run()

    assert result["id"] == slot.id
    session.refresh(slot)
    assert slot.start == Stamp(2101, 1, 2) and slot.key
    assert session.query(Episode).count() == 1


def test_episode_frame_needs_a_story(session):
    with pytest.raises(ValueError):
        GenerateFrame({}, ai=_Ai(seed=1)).run()


# ---------------------------------------------------------------- 本文

def test_episode_from_a_bare_draft_decides_the_frame_then_writes_the_body(session, place):
    story = session.query(Story).one()
    lead = _character(session, place, "甲", main_character=True)
    _character(session, place, "乙")
    ai = _Ai(seed=1)

    result = GenerateEpisode({"story_id": story.id}, ai=ai).run()

    record = session.get(Episode, result["id"])
    assert record.text == "甲は地図を買った。" and record.title  # 題は枠を決めたときのものが残る
    assert record.start == Stamp(2100, 6, 1) and "## 場面" in record.key and record.synced is True
    assert any(call["schema"] is frame_generator._FRAME_SCHEMA for call in ai.calls)
    # 登場人物を省けばメインキャラクター
    assert f'"name": "{lead.name}"' in _prompts(ai, episode_generator._SCHEMA)
    assert '"name": "乙"' not in _prompts(ai, episode_generator._SCHEMA)


def test_episode_with_key_and_time_skips_the_frame_step(session, place):
    story = session.query(Story).one()
    first = _character(session, place, "甲")
    ai = _Ai(seed=1)

    result = GenerateEpisode({"story_id": story.id, "key": "地図を買う", "start": str(WHEN), "title": "港の朝"},
                             character_ids=[first.id], ai=ai).run()

    record = session.get(Episode, result["id"])
    assert record.key == "地図を買う" and record.start == WHEN and record.title == "港の朝"
    assert record.text and result["letters"] == len(record.text)
    assert not any(call["schema"] is frame_generator._FRAME_SCHEMA for call in ai.calls)


def test_episode_writes_into_an_existing_empty_frame(session, place):
    story = session.query(Story).one()
    first = _character(session, place, "甲")
    slot = Episode(story_id=story.id, title="枠の題", key="地図を買う", start=WHEN)
    session.add(slot)
    session.commit()

    result = GenerateEpisode({"id": slot.id, "story_id": story.id, "key": "地図を買う", "start": str(WHEN),
                              "title": "枠の題", "text": "", "letters": 0, "synced": False},
                             character_ids=[first.id], ai=_Ai(seed=1)).run()

    assert result["id"] == slot.id
    session.refresh(slot)
    assert slot.text == "甲は地図を買った。" and slot.title == "枠の題"
    assert session.query(Episode).count() == 1


def test_episode_refuses_a_frame_that_already_has_a_body(session, place):
    story = session.query(Story).one()
    done = Episode(story_id=story.id, title="済", key="k", start=WHEN, text="本文")
    session.add(done)
    session.commit()
    with pytest.raises(ValueError):
        GenerateEpisode({"id": done.id}, character_ids=[1], ai=_Ai(seed=1)).run()


def test_episode_draft_is_saved_before_the_body_is_written_so_a_failure_keeps_it(session, place):
    story = session.query(Story).one()
    first = _character(session, place, "甲")

    with pytest.raises(RuntimeError):
        GenerateEpisode({"story_id": story.id, "key": "地図を買う", "start": str(WHEN), "title": "港の朝"},
                        character_ids=[first.id], ai=_FailingBodyAi(seed=1)).run()

    saved = session.query(Episode).one()
    assert saved.title == "港の朝" and saved.key == "地図を買う" and saved.start == WHEN and saved.text == ""


def test_episode_needs_characters_when_there_is_no_main_character(session, place):
    story = session.query(Story).one()
    _character(session, place, "甲")
    with pytest.raises(ValueError):
        GenerateEpisode({"story_id": story.id, "key": "k", "start": str(WHEN)}, ai=_Ai(seed=1)).run()


def test_episode_auto_selection_skips_unconfirmed_main_characters(session, place):
    story = session.query(Story).one()
    _character(session, place, "甲", main_character=True, confirmed=ConfirmStatus.PENDING)
    with pytest.raises(ValueError):
        GenerateEpisode({"story_id": story.id, "key": "k", "start": str(WHEN)}, ai=_Ai(seed=1)).run()


# ---------------------------------------------------------------- 推敲

def test_episode_revise_rewrites_the_existing_body(session, place):
    story = session.query(Story).one()
    first = _character(session, place, "甲")
    episode = Episode(story_id=story.id, title="港にて", key="地図を買う", start=WHEN, text="甲は市場を歩いた。")
    session.add(episode)
    session.commit()
    ai = _Ai(seed=1)

    result = ReviseEpisode({"id": episode.id}, character_ids=[first.id], instruction="外見を厚く書く", ai=ai).run()

    assert result["id"] == episode.id
    session.refresh(episode)
    assert episode.text == "書き直した後の本文。" and episode.title == "港にて"  # 題は空で返れば変えない
    assert session.query(Episode).count() == 1  # 新しい行を足さず、この行を直す
    prompt = _prompts(ai, episode_reviser._SCHEMA)
    assert "甲は市場を歩いた。" in prompt and "外見を厚く書く" in prompt


def test_episode_revise_refuses_when_the_body_is_empty(session, place):
    story = session.query(Story).one()
    first = _character(session, place, "甲")
    episode = Episode(story_id=story.id, title="", key="k", start=WHEN, text="")
    session.add(episode)
    session.commit()
    with pytest.raises(ValueError):
        ReviseEpisode({"id": episode.id}, character_ids=[first.id], instruction="外見を厚く書く", ai=_Ai(seed=1)).run()


def test_episode_revise_needs_characters_when_there_is_no_main_character(session, place):
    story = session.query(Story).one()
    _character(session, place, "甲")
    episode = Episode(story_id=story.id, title="", key="k", start=WHEN, text="本文")
    session.add(episode)
    session.commit()
    with pytest.raises(ValueError):
        ReviseEpisode({"id": episode.id}, instruction="外見を厚く書く", ai=_Ai(seed=1)).run()


def test_episode_revise_auto_selects_main_characters_when_character_ids_is_omitted(session, place):
    story = session.query(Story).one()
    lead = _character(session, place, "甲", main_character=True)
    _character(session, place, "乙")
    episode = Episode(story_id=story.id, title="港にて", key="地図を買う", start=WHEN, text="甲は市場を歩いた。")
    session.add(episode)
    session.commit()
    ai = _Ai(seed=1)

    result = ReviseEpisode({"id": episode.id}, instruction="外見を厚く書く", ai=ai).run()

    assert result["id"] == episode.id
    prompt = _prompts(ai, episode_reviser._SCHEMA)
    # 登場人物を省けばメインキャラクター(GenerateEpisode と同じ選び方)
    assert f'"name": "{lead.name}"' in prompt and '"name": "乙"' not in prompt


def test_episode_revise_also_saves_the_drafted_title_and_key(session, place):
    story = session.query(Story).one()
    first = _character(session, place, "甲")
    episode = Episode(story_id=story.id, title="旧題", key="旧key", start=WHEN, text="甲は市場を歩いた。")
    session.add(episode)
    session.commit()

    result = ReviseEpisode({"id": episode.id, "title": "新題", "key": "新key"},
                           character_ids=[first.id], instruction="外見を厚く書く", ai=_Ai(seed=1)).run()

    assert result["id"] == episode.id
    session.refresh(episode)
    assert episode.title == "新題" and episode.key == "新key" and episode.text == "書き直した後の本文。"


def test_episode_revise_draft_is_saved_before_the_ai_call_so_a_failure_keeps_it(session, place):
    story = session.query(Story).one()
    first = _character(session, place, "甲")
    episode = Episode(story_id=story.id, title="旧題", key="旧key", start=WHEN, text="甲は市場を歩いた。")
    session.add(episode)
    session.commit()

    with pytest.raises(RuntimeError):
        ReviseEpisode({"id": episode.id, "title": "新題", "key": "新key"},
                      character_ids=[first.id], instruction="外見を厚く書く", ai=_FailingReviseAi(seed=1)).run()

    session.refresh(episode)
    assert episode.title == "新題" and episode.key == "新key" and episode.text == "甲は市場を歩いた。"


def test_episode_revise_needs_instruction(session, place):
    story = session.query(Story).one()
    first = _character(session, place, "甲")
    episode = Episode(story_id=story.id, title="", key="k", start=WHEN, text="本文")
    session.add(episode)
    session.commit()
    with pytest.raises(ValueError):
        ReviseEpisode({"id": episode.id}, character_ids=[first.id], instruction="  ", ai=_Ai(seed=1)).run()
