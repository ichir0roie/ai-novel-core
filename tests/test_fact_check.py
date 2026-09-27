"""アイデア・ミームを AI に Dラボ・ネット検索で検めさせ、妥当性と補足を本文末尾の `# 検証結果` の節へ書く。"""

import pytest

from ai.claude_code import ai_client, fact_checker
from ai.claude_code.interface.meme import extract_memes
from ai.claude_code.interface.meme.extract_memes import ExtractMemes
from ai.claude_code.interface.randomizer.commit_idea import CommitIdea
from ai.claude_code.interface.fact_check.check_facts import CheckFacts
from ai.claude_code.interface.randomizer.commit_oracle import CommitOracle
from ai.time_keeper import meme
from db.schema import Idea, Meme, Oracle


class _FactChecker:
    """道具つきの呼び出し(検める)には、渡された番号ぶん `検めた:<本文の最後の行>` を返す。
    道具なしの呼び出し(ミームの抜き出し)には、渡されていれば `memes` を返す。"""

    def __init__(self, memes=None):
        self.calls = []
        self.memes = memes


    def __call__(self, prompt, schema, **kwargs):
        if not kwargs.get("tools"):
            if self.memes and "memes" in schema["properties"]:
                return {"memes": self.memes}
            return {"duplicates": []} if "duplicates" in schema["properties"] else {}
        self.calls.append((prompt, kwargs))
        blocks = prompt.split("\n\n")[:-1]
        return {"results": [
            {"number": number, "fact_check": f"## 妥当性\n検めた:{block.splitlines()[-1]}"}
            for number, block in enumerate(blocks, start=1)]}


@pytest.fixture
def fake_check(monkeypatch):
    fake = _FactChecker()
    monkeypatch.setattr(ai_client, "try_generate_json", fake)
    return fake


def test_build_args_allows_given_tools_only(monkeypatch):
    monkeypatch.setenv("DEM_CLAUDE_AI_MCP_CONFIG", "mcp.json")
    plain = ai_client._build_args(None, None)
    assert plain[plain.index("--tools") + 1] == ""
    assert "--allowedTools" not in plain and "--mcp-config" not in plain

    web = ai_client._build_args(None, None, ("WebSearch", "WebFetch"))
    assert web[web.index("--tools") + 1] == "WebSearch,WebFetch"
    assert web[web.index("--allowedTools") + 1] == "WebSearch,WebFetch"
    assert "--mcp-config" not in web

    # MCP の道具は組み込みの `--tools` に混ぜず、許可と MCP の設定だけを渡す
    mcp = ai_client._build_args(None, None, ("WebSearch", "mcp__d-lab"))
    assert mcp[mcp.index("--tools") + 1] == "WebSearch"
    assert mcp[mcp.index("--allowedTools") + 1] == "WebSearch,mcp__d-lab"
    assert mcp[mcp.index("--mcp-config") + 1] == "mcp.json"


def test_build_args_defaults_to_sonnet_medium():
    args = ai_client._build_args(None, None)
    assert args[args.index("--model") + 1] == "claude-sonnet-5"
    assert args[args.index("--effort") + 1] == "medium"

    args = ai_client._build_args(None, None, model="claude-fable-5-1", effort="high")
    assert args[args.index("--model") + 1] == "claude-fable-5-1"
    assert args[args.index("--effort") + 1] == "high"


def test_check_tools_include_dlab(monkeypatch):
    monkeypatch.delenv("DEM_CLAUDE_AI_DLAB_TOOLS", raising=False)
    assert fact_checker.tools() == ("WebSearch", "WebFetch", "ToolSearch", "mcp__d-lab")

    monkeypatch.setenv("DEM_CLAUDE_AI_DLAB_TOOLS", "mcp__claude_ai_D-Lab, mcp__x")
    assert fact_checker.tools()[-2:] == ("mcp__claude_ai_D-Lab", "mcp__x")

    monkeypatch.setenv("DEM_CLAUDE_AI_DLAB_TOOLS", "")
    assert fact_checker.tools() == fact_checker.WEB_TOOLS


def test_check_fills_only_unreviewed_with_text(session, fake_check):
    session.add_all([
        Idea(name="魔力", kind="概念", text="大気に満ちる力"),
        Idea(name="済み", kind="概念", text="検めてある\n\n# 検証結果\n前の結果"),
        Idea(name="空", kind="概念", text=""),
    ])
    session.commit()

    assert CheckFacts("idea").run() == {"checked": 1, "memes_added": 0}

    session.expire_all()
    rows = {row.name: row.text for row in session.query(Idea).all()}
    assert rows == {
        "魔力": "大気に満ちる力\n\n# 検証結果\n## 妥当性\n検めた:大気に満ちる力",
        "済み": "検めてある\n\n# 検証結果\n前の結果",
        "空": "",
    }
    prompt, kwargs = fake_check.calls[0]
    assert "アイデア「魔力」" in prompt
    assert kwargs["tools"] == fact_checker.tools()


def test_check_by_ids_redoes_reviewed(session, fake_check):
    meme = Meme(text="約束は守る\n\n# 検証結果\n古い結果", category="信条")
    session.add(meme)
    session.commit()

    assert CheckFacts("meme", ids=[meme.id]).run() == {"checked": 1, "memes_added": 0}

    session.expire_all()
    assert session.get(Meme, meme.id).text == "約束は守る\n\n# 検証結果\n## 妥当性\n検めた:約束は守る"


def test_check_keeps_empty_when_ai_fails(session):
    session.add(Meme(text="約束は守る", category="信条"))
    session.commit()

    assert CheckFacts("meme").run() == {"checked": 0, "memes_added": 0}
    session.expire_all()
    assert session.query(Meme).one().text == "約束は守る"


def test_check_rejects_unknown_table():
    with pytest.raises(ValueError, match="table は"):
        CheckFacts("event")


def test_commit_idea_checks_idea_and_new_memes(session, monkeypatch):
    session.add(Meme(text="古いミーム", category="信条"))
    session.commit()
    fake = _FactChecker(memes=[{"text": "灯りは分け合う", "category": "信条"}])
    monkeypatch.setattr(ai_client, "try_generate_json", fake)

    result = CommitIdea({"name": "魔力灯り", "kind": "技術", "text": "魔力で灯る明かり"}).run()

    assert result["memes_added"] == 1
    assert result["text"] == "魔力で灯る明かり\n\n# 検証結果\n## 妥当性\n検めた:魔力で灯る明かり"
    session.expire_all()
    texts = {meme.text for meme in session.query(Meme).all()}
    assert texts == {"古いミーム", "灯りは分け合う\n\n# 検証結果\n## 妥当性\n検めた:灯りは分け合う"}


def test_commit_idea_skips_check_when_asked(session, fake_check):
    result = CommitIdea({"name": "外部デバイス", "kind": "技術", "text": "身体アシスト"}, fact_check=False).run()

    assert result["text"] == "身体アシスト"
    assert fake_check.calls == []


def test_commit_oracle_checks_oracle_and_new_memes(session, monkeypatch):
    fake = _FactChecker(memes=[{"text": "書くことで考える", "category": "信条"}])
    monkeypatch.setattr(ai_client, "try_generate_json", fake)

    result = CommitOracle({"text": "毎朝書く"}).run()

    assert result["text"] == "毎朝書く\n\n# 検証結果\n## 妥当性\n検めた:毎朝書く"
    assert [call[0].splitlines()[1] for call in fake.calls] == ["覚え書き(oracle)", "ミーム(分類: 信条)"]
    session.expire_all()
    assert session.query(Meme).one().text == "書くことで考える\n\n# 検証結果\n## 妥当性\n検めた:書くことで考える"
    assert session.query(Oracle).one().meme_seeded


def test_memes_are_drawn_from_text_including_fact_check(session, monkeypatch):
    prompts = []

    def extract(prompt, schema, **kwargs):
        prompts.append(prompt)
        return {"memes": []}

    monkeypatch.setattr(ai_client, "try_generate_json", extract)
    session.add_all([
        Idea(name="魔力", kind="概念", text="大気に満ちる力\n\n# 検証結果\n## 補足\n錬金術師は秘密を守った"),
        Oracle(text="毎朝書く"),
    ])
    session.commit()

    meme.refresh(session, ai_client)

    assert "## 元1(idea)\n大気に満ちる力\n\n# 検証結果\n## 補足\n錬金術師は秘密を守った" in prompts[0]
    assert "## 元2(oracle)\n毎朝書く" in prompts[0]


def test_record_is_unseeded_when_extraction_fails(session, monkeypatch):
    monkeypatch.setattr(ai_client, "try_generate_json", lambda *a, **k: {})
    idea = Idea(name="魔力", kind="概念", text="大気に満ちる力\n\n# 検証結果\n錬金術師は秘密を守った")
    session.add(idea)
    session.commit()

    meme.refresh(session, ai_client)

    session.expire_all()
    assert not session.get(Idea, idea.id).meme_seeded


def test_check_resets_meme_seeded_and_extracts_from_result(session, monkeypatch):
    idea = Idea(name="魔力", kind="概念", text="大気に満ちる力", meme_seeded=True)
    session.add(idea)
    session.commit()
    fake = _FactChecker(memes=[{"text": "秘密は力になる", "category": "信条"}])
    monkeypatch.setattr(ai_client, "try_generate_json", fake)

    assert CheckFacts("idea").run() == {"checked": 1, "memes_added": 1}

    session.expire_all()
    assert session.get(Idea, idea.id).meme_seeded
    assert session.query(Meme).one().text == "秘密は力になる\n\n# 検証結果\n## 妥当性\n検めた:秘密は力になる"


def test_extract_memes_checks_only_new(session, fake_check, monkeypatch):
    old = Meme(text="古いミーム", category="信条")
    session.add(old)
    session.commit()

    def refresh(s, ai):
        s.add(Meme(text="新しいミーム", category="欲求"))
        s.commit()
        return 1

    monkeypatch.setattr(extract_memes._meme, "refresh", refresh)
    assert ExtractMemes().run() == 1

    session.expire_all()
    texts = {meme.text for meme in session.query(Meme).all()}
    assert texts == {"古いミーム", "新しいミーム\n\n# 検証結果\n## 妥当性\n検めた:新しいミーム"}
