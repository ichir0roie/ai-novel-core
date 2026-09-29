"""テストは `novel.test.db` だけを読み書きする。`tool.test` を最初に import して db パスを固定する。"""
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from tool.test import copy_novel_db  # schema より先に読む(db を novel.test.db に固定)
from tool.test.mock_ai_client import MockAIClient  # noqa: E402
from db.schema import (  # noqa: E402
    Character, CharacterHistory, CharacterParameter, CharacterLocation, CharacterRelation, ConfirmStatus, Episode,
    EpisodeCharacter, Event, EventCharacter, EventSeed, Idea, IdeaRecognition, Location, Meme, MemeCategory, Oracle,
    Story, engine, get_env_session,
)
from data_access_logic.entrypoint import Entrypoint  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def fresh_test_db() -> None:
    copy_novel_db()
    engine.dispose()  # 写す前のファイルを掴んでいる接続を捨てる


@pytest.fixture(autouse=True)
def mock_ai(monkeypatch: pytest.MonkeyPatch) -> MockAIClient:
    """入口は `ai` を省くと `ai.claude_code.ai_client` を使うので、その `generate` をモックへ差し替える。"""
    from ai.claude_code import ai_client
    mock = MockAIClient(seed=0)
    monkeypatch.setattr(ai_client, "generate", mock.generate)
    return mock


@pytest.fixture
def shown(capsys: pytest.CaptureFixture[str]) -> Callable[[Entrypoint], Any]:
    """claude が CLI から呼ぶのと同じく `show()` を呼び、標準出力の JSON を読んで返す。"""
    def show(entrypoint: Entrypoint) -> Any:
        capsys.readouterr()
        entrypoint.show()
        return json.loads(capsys.readouterr().out)
    return show


@dataclass
class World:
    planet_id: int
    location_id: int
    neighbor_id: int
    story_id: int
    character_ids: list[int]
    character_location_id: int
    relation_id: int
    event_id: int
    child_event_id: int
    episode_id: int
    idea_id: int
    child_idea_id: int
    meme_id: int
    oracle_id: int
    event_seed_id: int


def _parameter(start: str | None, end: str | None, sex: str) -> CharacterParameter:
    return CharacterParameter(
        start=start, end=end, family_name="テスト家", sex=sex, height=170.5, build="細身",
        first_person="私", second_person="あなた", third_person="あの人", tone="丁寧", dialect="標準語",
        sincerity="高", curiosity="並", proactivity="低", cooperativeness="高", sociability="並",
        emotional_expression="低", self_esteem="並", self_efficacy="高", stress_resilience="並",
        flexibility_of_values="低", sensitivity="高", imagination="必")


@pytest.fixture
def world() -> Iterator[World]:
    """テストごとに、互いに結び付いた一揃いの行(星・場所・作品・人物・出来事・話・アイデアなど)を足す。
    写した本番の行と混ざっても、返した id で自分の行を指せる。"""
    with get_env_session() as s:
        planet = Location(name="テスト星", kind="星", text="テスト用の星", area=500000000, start="1000", end="3000")
        s.add(planet)
        s.flush()
        location = Location(
            name="テスト都", kind="都市", text="テスト用の都", parent_id=planet.id, location_world=1,
            location_planet=planet.id, location_longitude=135.5, location_latitude=35.0, location_altitude=50,
            area=1000, environment="温帯", sample_region="地中海沿岸", sample_culture="都市国家",
            sample_era="中世", start="1100", end="2900", active_random_generation=True)
        s.add(location)
        s.flush()
        neighbor = Location(
            name="テスト村", kind="村", text="テスト用の村", parent_id=planet.id, location_world=1,
            location_planet=planet.id, location_longitude=136.0, location_latitude=35.5, location_altitude=300,
            polygon={"type": "Polygon", "coordinates": [[[135.9, 35.4], [136.1, 35.4], [136.1, 35.6], [135.9, 35.4]]]},
            area=100, environment="山地", start="1150")
        s.add(neighbor)
        s.flush()
        story = Story(name="テスト作品", text="テスト用の作品", world_id=planet.id, location_id=location.id,
                      narration="三人称", state="執筆中", start="1200/01/01", end="1300/01/01", event_seeded=True)
        s.add(story)
        characters = [
            Character(name=name, text=f"{name}の説明", kind="人物", confirmed=ConfirmStatus.APPROVED,
                      main_character=main, event_seeded=True, meme_seeded=True,
                      parameters=[_parameter("1170/01/01", "1260/01/01", sex)],
                      histories=[CharacterHistory(start="1190/01/01", end="1250/01/01", description=f"{name}の来歴")])
            for name, sex, main in (("テスト太郎", "男", True), ("テスト花子", "女", False))]
        s.add_all(characters)
        s.flush()
        character_locations = [CharacterLocation(character_id=character.id, location_id=location.id, start="1170/01/01")
                            for character in characters]
        s.add_all(character_locations)
        relation = CharacterRelation(character_1_id=characters[0].id, character_2_id=characters[1].id,
                                     relation="幼なじみ", text="同じ通りで育った", start="1175/01/01")
        s.add(relation)
        event = Event(name="テスト市", text="市が立った", hidden=False, confirmed=ConfirmStatus.APPROVED,
                      time="1200/04/01 12:00:00", location_id=location.id, start="1200/04/01", end="1200/04/02",
                      event_seeded=True, meme_seeded=True,
                      event_characters=[EventCharacter(character_id=character.id) for character in characters])
        s.add(event)
        s.flush()
        child_event = Event(name="テスト取引", text="取引がまとまった", confirmed=ConfirmStatus.APPROVED,
                            time="1200/04/01 15:00:00", location_id=location.id, parent_event_id=event.id,
                            event_seeded=True, meme_seeded=True)
        s.add(child_event)
        episode = Episode(story_id=story.id, title="テスト第一話", key="市で出会う", text="市で二人が出会った。",
                          synced=True, start="1200/04/01 12:00:00", end="1200/04/01 18:00:00",
                          viewpoint_character_id=characters[0].id, location_id=location.id, event_seeded=True)
        s.add(episode)
        s.flush()
        s.add_all([EpisodeCharacter(episode_id=episode.id, character_id=character.id) for character in characters])
        idea = Idea(name="テスト魔導", kind="技術", text="テスト用の技術", confirmed=ConfirmStatus.APPROVED,
                    location_id=location.id, start="1100/01/01", meme_seeded=True,
                    recognitions=[IdeaRecognition(location_id=location.id, start="1150/01/01", name="テスト術",
                                                  detail="都での呼び名")])
        s.add(idea)
        s.flush()
        child_idea = Idea(name="テスト魔導炉", kind="技術", text="テスト魔導の炉", confirmed=ConfirmStatus.PENDING,
                          location_id=location.id, parent_idea_id=idea.id, meme_seeded=True)
        meme = Meme(text="テストの信条", category=MemeCategory.BELIEF, confirmed=ConfirmStatus.PENDING)
        oracle = Oracle(title="テストの覚え書き", text="テスト用の覚え書き", meme_seeded=True)
        event_seed = EventSeed(text="テストの種", consolidated=False)
        s.add_all([child_idea, meme, oracle, event_seed])
        s.commit()
        yield World(
            planet_id=planet.id, location_id=location.id, neighbor_id=neighbor.id, story_id=story.id,
            character_ids=[character.id for character in characters], character_location_id=character_locations[0].id,
            relation_id=relation.id, event_id=event.id, child_event_id=child_event.id, episode_id=episode.id,
            idea_id=idea.id, child_idea_id=child_idea.id, meme_id=meme.id, oracle_id=oracle.id,
            event_seed_id=event_seed.id)
