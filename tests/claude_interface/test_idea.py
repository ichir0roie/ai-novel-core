"""claude が CLI から `show()` で呼ぶ、アイデア(`data_access_logic/idea/`)と事実の検め(`fact_check/`)の入口。"""
from ai.claude_code import ai_client, fact_checker
from data_access_logic.fact_check.check_facts import CheckFacts
from data_access_logic.idea.commit_idea import CommitIdea
from data_access_logic.idea.delete_idea import DeleteIdea
from data_access_logic.idea.form import IdeaCreateForm, IdeaUpdateForm
from data_access_logic.idea.link_ideas import LinkIdeas
from data_access_logic.idea.merge_idea import MergeIdea
from data_access_logic.idea.models import IdeaDraft
from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.idea.resolve_ideas import ResolveIdeas
from data_access_logic.idea.search_ideas import SearchIdeas
from data_access_logic.idea.update_idea import UpdateIdea


def test_check_facts(shown, world, mock_ai, monkeypatch):
    def generate(prompt, output, *args, **kwargs):
        # モックは配列を空で返すので、検めの応答だけは渡した番号ぶん埋める
        if output is fact_checker.FactChecksDraft:
            return output(results=[fact_checker.FactCheckDraft(number=number, fact_check=f"## 妥当性\n検めた{number}")
                                   for number in (1, 2)])
        return mock_ai.generate(prompt, output, *args, **kwargs)
    monkeypatch.setattr(ai_client, "generate", generate)

    result = shown(CheckFacts(table="idea", ids=[world.idea_id, world.child_idea_id], limit=2))

    assert result["checked"] == 2
    assert isinstance(result["memes_added"], int)
    found = {idea["id"]: idea for idea in shown(SearchIdeas(keywords=[IdeaDraft(keyword="テスト魔導")]))}
    for idea_id in (world.idea_id, world.child_idea_id):
        assert f"{fact_checker.FACT_CHECK_HEADING}\n## 妥当性\n検めた" in found[idea_id]["text"]


def test_commit_idea(shown, world, mock_ai):
    result = shown(CommitIdea(IdeaCreateForm(
        name="テスト飛空艇", kind="技術", text="空を渡る船", location_id=world.location_id,
        start="1190/01/01", end="1290/01/01", parent_idea_id=world.idea_id, meme_seeded=False,
        histories=[IdeaHistoryRow(location_id=world.location_id, start="1195/01/01", end="1250/01/01",
                                         name="空舟", detail="都の俗称")]),
        fact_check=True))

    record = result["record"]
    assert (record["name"], record["kind"]) == ("テスト飛空艇", "技術")
    assert record["text"].startswith("空を渡る船")
    assert (record["location_id"], record["parent_idea_id"]) == (world.location_id, world.idea_id)
    assert (record["start"], record["end"]) == ("1190/01/01 00:00:00", "1290/01/01 00:00:00")
    assert record["histories"] == [{"location_id": world.location_id, "start": "1195/01/01 00:00:00",
                                       "end": "1250/01/01 00:00:00", "name": "空舟", "detail": "都の俗称",
                                       "knowers": []}]
    assert isinstance(result["memes_added"], int)
    assert mock_ai.calls


def test_delete_idea(shown, world):
    result = shown(DeleteIdea(idea_id=world.child_idea_id))

    assert result == {"id": world.child_idea_id, "name": "テスト魔導炉", "kind": "技術"}


def test_link_ideas(shown, world):
    result = shown(LinkIdeas(idea_ids=[world.idea_id, world.child_idea_id], episode_id=world.episode_id))

    assert result == {"episode_id": world.episode_id, "linked": 2}


def test_merge_idea(shown, world):
    result = shown(MergeIdea(source_id=world.child_idea_id, target_id=world.idea_id))

    assert result["merged"]["id"] == world.child_idea_id
    assert result["into"]["id"] == world.idea_id
    assert isinstance(result["links_moved"], int)


def test_resolve_ideas(shown, world):
    result = shown(ResolveIdeas(
        ideas=[IdeaDraft(keyword="テスト魔導", variants=["テスト術"], description="都の技術", coined=True, kind="技術",
                        start="1100"),
               IdeaDraft(keyword="テスト新語", variants=["テスト新語法"], description="まだ無い語", coined=True, kind="概念",
                        start="1200", end="1300")],
        location_id=world.location_id, time="1200/04/01"))

    assert world.idea_id in result["hits"]
    assert [candidate["name"] for candidate in result["candidates"]] == ["テスト新語"]


def test_search_ideas(shown, world):
    result = shown(SearchIdeas(
        keywords=[IdeaDraft(keyword="テスト魔導", variants=["テスト術", "魔導炉"], description="都の技術", kind="技術")],
        location_id=world.location_id, limit=5, time="1200/04/01"))

    found = {idea["id"]: idea for idea in result}
    assert world.idea_id in found
    assert found[world.idea_id]["called"] == "テスト術"


def test_update_idea(shown, world):
    result = shown(UpdateIdea(IdeaUpdateForm(
        id=world.child_idea_id, name="テスト魔導機関", kind="機関", text="炉を改めた機関",
        location_id=world.neighbor_id, start="1150/01/01", end="1250/01/01", parent_idea_id=world.idea_id,
        meme_seeded=False,
        histories=[IdeaHistoryRow(location_id=world.neighbor_id, start="1160/01/01", end=None,
                                         name="釜", detail="村での呼び名")])))

    assert (result["name"], result["kind"], result["text"]) == ("テスト魔導機関", "機関", "炉を改めた機関")
    assert (result["location_id"], result["parent_idea_id"]) == (world.neighbor_id, world.idea_id)
    assert (result["start"], result["end"]) == ("1150/01/01 00:00:00", "1250/01/01 00:00:00")
    assert result["meme_seeded"] is False
    assert [history["name"] for history in result["histories"]] == ["釜"]
