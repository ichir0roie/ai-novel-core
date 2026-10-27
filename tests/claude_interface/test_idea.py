"""claude が CLI から `show()` で呼ぶ、アイデア(`data_access_logic/idea/`)と事実の検め(`fact_check/`)の入口。"""
import pytest

from ai.claude_code import ai_client, fact_checker
from data_access_logic.fact_check.check_facts import CheckFacts
from data_access_logic.idea.commit_idea import CommitIdea
from data_access_logic.idea.delete_idea import DeleteIdea
from data_access_logic.idea.form import IdeaCreateForm, IdeaUpdateForm
from data_access_logic.idea.merge_idea import MergeIdea
from data_access_logic.idea.models import (
    IdeaContextSerialized, IdeaDraft, IdeaMaterial, RelatedIdeaMaterial, idea_for_prompt,
)
from data_access_logic.idea.record import IdeaHistoryRow
from data_access_logic.idea.resolve_ideas import ResolveIdeas
from data_access_logic.idea.search_ideas import SearchIdeas
from data_access_logic.idea.update_idea import UpdateIdea
from db.schema import Idea, Oracle, get_env_session


def test_check_facts(shown, world, mock_ai, monkeypatch):
    def generate(prompt, output, *args, **kwargs):
        # モックは配列を空で返すので、検めの応答だけは渡した番号ぶん埋める
        if output is fact_checker.FactChecksDraft:
            return output(results=[fact_checker.FactCheckDraft(number=1, fact_check="## 妥当性\n検めた1")])
        return mock_ai.generate(prompt, output, *args, **kwargs)
    monkeypatch.setattr(ai_client, "generate", generate)

    result = shown(CheckFacts(table="oracle", ids=[world.oracle_id]))

    assert result == {"checked": 1}
    with get_env_session() as s:
        assert f"{fact_checker.FACT_CHECK_HEADING}\n## 妥当性\n検めた1" in s.get_one(Oracle, world.oracle_id).text


def test_check_facts_skips_ideas():
    # アイデアの本文は作者だけが読むので、AI に検めさせない
    with pytest.raises(ValueError, match="table"):
        CheckFacts(table="idea")


def test_commit_idea(shown, world, mock_ai):
    result = shown(CommitIdea(IdeaCreateForm(
        name="テスト飛空艇", kind="技術", text="空を渡る船", parent_idea_id=world.idea_id,
        histories=[IdeaHistoryRow(location_id=world.location_id, start="1195/01/01", end="1250/01/01",
                                  name="空舟", detail="都の俗称")])))

    assert (result["name"], result["kind"], result["text"]) == ("テスト飛空艇", "技術", "空を渡る船")
    assert result["parent_idea_id"] == world.idea_id
    assert "start" not in result
    assert [{key: value for key, value in row.items() if key != "id"} for row in result["histories"]] == [
        {"location_id": world.location_id, "start": "1195/01/01 00:00:00", "end": "1250/01/01 00:00:00",
         "name": "空舟", "detail": "都の俗称", "knowers": []}]
    # 本文は作者だけが読むので、確定のあとに AI を回さない
    assert not mock_ai.calls


def test_delete_idea(shown, world):
    result = shown(DeleteIdea(idea_id=world.child_idea_id))

    assert result == {"id": world.child_idea_id, "name": "テスト魔導炉", "kind": "技術"}


def test_merge_idea(shown, world):
    result = shown(MergeIdea(source_id=world.child_idea_id, target_id=world.idea_id))

    assert result["merged"]["id"] == world.child_idea_id
    assert result["into"]["id"] == world.idea_id


def test_resolve_ideas(shown, world):
    result = shown(ResolveIdeas(
        ideas=[IdeaDraft(keyword="テスト魔導", variants=["テスト術"], description="都の技術", coined=True, kind="技術",
                         start="1100"),
               IdeaDraft(keyword="テスト新語", variants=["テスト新語法"], description="まだ無い語", coined=True, kind="概念",
                         start="1200", end="1300")],
        location_id=world.location_id, time="1200/04/01"))

    assert world.idea_id in result["hits"]
    assert [candidate["name"] for candidate in result["candidates"]] == ["テスト新語"]
    # 候補の効く期間は履歴の行に入る
    with get_env_session() as s:
        added = s.get_one(Idea, result["candidates"][0]["id"])
        assert [(str(row.start), str(row.end)) for row in added.histories] == [
            ("1200/01/01 00:00:00", "1300/01/01 00:00:00")]


def test_candidate_without_period_starts_at_the_text_time(shown, world):
    result = shown(ResolveIdeas(
        ideas=[IdeaDraft(keyword="テスト時期なし語", description="時期の言えない語", coined=True, kind="概念")],
        location_id=world.location_id, time="1200/04/01"))

    # 時期を言えない語は、語の出た文の時刻から効く(始まりを空けると、次から時期未定として引けなくなる)
    with get_env_session() as s:
        added = s.get_one(Idea, result["candidates"][0]["id"])
        assert [str(row.start) for row in added.histories] == ["1200/04/01 00:00:00"]


def test_search_ideas(shown, world):
    result = shown(SearchIdeas(
        keywords=[IdeaDraft(keyword="テスト魔導", variants=["テスト術", "魔導炉"], description="都の技術", kind="技術")],
        # 前の回の world のアイデア(同じ名前で、どこでも効く行を持つことがある)も当たるので、件数を絞らない
        location_id=world.location_id, time="1200/04/01"))

    found = {idea["id"]: idea for idea in result}
    assert world.idea_id in found
    assert found[world.idea_id]["called"] == "テスト術"


def test_update_idea(shown, world):
    result = shown(UpdateIdea(IdeaUpdateForm(
        id=world.child_idea_id, name="テスト魔導機関", kind="機関", text="炉を改めた機関", parent_idea_id=world.idea_id,
        histories=[IdeaHistoryRow(location_id=world.neighbor_id, start="1160/01/01", end=None,
                                  name="釜", detail="村での呼び名")])))

    assert (result["name"], result["kind"], result["text"]) == ("テスト魔導機関", "機関", "炉を改めた機関")
    assert result["parent_idea_id"] == world.idea_id
    assert [history["name"] for history in result["histories"]] == ["釜"]


def test_idea_scope_follows_history_rows(shown, world):
    # 本体は場所も時期も持たず、履歴の行の場所・期間で絞る。場所の空いた行はどこでも当たる
    far = shown(CommitIdea(IdeaCreateForm(name="テスト村の技", kind="技術", text="村だけの技", histories=[
        IdeaHistoryRow(location_id=world.neighbor_id, start="1100/01/01", name="テスト村の技")])))
    anywhere = shown(CommitIdea(IdeaCreateForm(name="テストどこでも技", kind="技術", text="どこでもの技", histories=[
        IdeaHistoryRow(start="1100/01/01", name="テストどこでも技")])))
    later = shown(CommitIdea(IdeaCreateForm(name="テスト後の技", kind="技術", text="後の時代の技", histories=[
        IdeaHistoryRow(start="1300/01/01", name="テスト後の技")])))

    result = shown(SearchIdeas(
        keywords=[IdeaDraft(keyword="テスト村の技", variants=["テストどこでも技", "テスト後の技"], description="技",
                            kind="技術")],
        location_id=world.location_id, time="1200/04/01"))

    found = {idea["id"] for idea in result}
    assert anywhere["id"] in found and far["id"] not in found and later["id"] not in found


def test_undated_ideas_are_left_out_at_a_time(shown, world):
    # 始まりの空いた行しか無いアイデアと、履歴の行の無いアイデアは、時刻を渡すと時期未定として外れる
    undated = shown(CommitIdea(IdeaCreateForm(name="テスト時期未定の技", kind="技術", text="いつからか分からない技",
                                              histories=[IdeaHistoryRow(name="テスト時期未定の技")])))
    bare = shown(CommitIdea(IdeaCreateForm(name="テスト履歴無しの技", kind="技術", text="行の無い技")))
    keywords = [IdeaDraft(keyword="テスト時期未定の技", variants=["テスト履歴無しの技"], description="技", kind="技術")]

    at_time = {idea["id"] for idea in shown(SearchIdeas(keywords=keywords, location_id=world.location_id,
                                                        time="1200/04/01"))}
    anytime = {idea["id"] for idea in shown(SearchIdeas(keywords=keywords, location_id=world.location_id))}

    assert not {undated["id"], bare["id"]} & at_time
    assert {undated["id"], bare["id"]} <= anytime


def test_generation_prompts_omit_idea_text(world):
    with get_env_session() as s:
        related = RelatedIdeaMaterial(idea=IdeaMaterial.model_validate(s.get_one(Idea, world.idea_id)))

    # 生成に渡す形には本文を載せず、語り部と話を書く Claude の材料にだけ載せる
    assert "内容" not in IdeaContextSerialized(hits=[], candidates=[], related=[related]).model_dump()[0]
    assert idea_for_prompt(related, with_text=True)["内容"] == "テスト用の技術"
