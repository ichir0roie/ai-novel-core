"""claude が CLI から `show()` で呼ぶ、ミーム(`data_access_logic/meme/`)・覚え書き(`oracle/`)・レビュー(`review/`)の入口。"""
from data_access_logic.meme.commit_meme import CommitMeme
from data_access_logic.meme.delete_meme import DeleteMeme
from data_access_logic.meme.draw_memes import DrawMemes
from data_access_logic.meme.extract_memes import ExtractMemes
from data_access_logic.meme.form import MemeCreateForm, MemeUpdateForm
from data_access_logic.meme.refresh_generated_content import RefreshGeneratedContent
from data_access_logic.meme.update_meme import UpdateMeme
from data_access_logic.oracle.commit_oracle import CommitOracle
from data_access_logic.oracle.form import OracleCreateForm, OracleUpdateForm
from data_access_logic.oracle.update_oracle import UpdateOracle
from data_access_logic.review.list_pending_reviews import ListPendingReviews
from db.schema import ConfirmStatus, MemeCategory


def test_commit_meme(shown):
    result = shown(CommitMeme(MemeCreateForm(
        text="約束は命より重い", category=MemeCategory.BELIEF, confirmed=ConfirmStatus.PENDING)))

    assert (result["text"], result["category"], result["confirmed"]) == ("約束は命より重い", "信条", "未確認")


def test_delete_meme(shown, world):
    result = shown(DeleteMeme(meme_id=world.meme_id))

    assert result == {"id": world.meme_id, "category": "信条", "confirmed": "未確認", "text": "テストの信条"}


def test_draw_memes(shown, world):
    UpdateMeme(MemeUpdateForm(id=world.meme_id, confirmed=ConfirmStatus.APPROVED)).run()

    result = shown(DrawMemes(person=True, seed=4))

    assert isinstance(result, list)
    assert result == shown(DrawMemes(person=True, seed=4))


def test_extract_memes(shown, mock_ai):
    result = shown(ExtractMemes(fact_check=True))

    assert isinstance(result["memes_added"], int)
    assert mock_ai.calls


def test_refresh_generated_content(shown, world, mock_ai):
    result = shown(RefreshGeneratedContent())

    assert set(result) == {"memes_added", "events_summarized", "episodes_summarized"}
    # fixture で足した出来事・話は要約が無いので、ここで作る
    assert result["events_summarized"] >= 2
    assert result["episodes_summarized"] >= 1
    assert mock_ai.calls


def test_update_meme(shown, world):
    result = shown(UpdateMeme(MemeUpdateForm(
        id=world.meme_id, text="約束は守る", category=MemeCategory.LAW, confirmed=ConfirmStatus.APPROVED)))

    assert result == {"id": world.meme_id, "category": "理", "confirmed": "承認", "text": "約束は守る"}


def test_commit_oracle(shown, mock_ai):
    result = shown(CommitOracle(
        OracleCreateForm(text="書く前に結末を決める", title="結末の覚え書き", meme_seeded=False), fact_check=True))

    record = result["record"]
    assert record["title"] == "結末の覚え書き"
    assert record["text"].startswith("書く前に結末を決める")
    assert isinstance(result["memes_added"], int)
    assert mock_ai.calls


def test_update_oracle(shown, world):
    result = shown(UpdateOracle(OracleUpdateForm(
        id=world.oracle_id, text="直した覚え書き", title="直した題", meme_seeded=False)))

    assert result == {"id": world.oracle_id, "title": "直した題", "meme_seeded": False, "text": "直した覚え書き"}


def test_list_pending_reviews(shown, world):
    result = shown(ListPendingReviews())

    assert {"key", "kind", "title", "detail"} <= set(result[0])
    assert any("テスト魔導炉" in item["title"] for item in result)
