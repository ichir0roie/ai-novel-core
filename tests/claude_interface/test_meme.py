"""claude が CLI から `show()` で呼ぶ、ミーム(`data_access_logic/meme/`)・覚え書き(`oracle/`)・レビュー(`review/`)の入口。"""
import json

import pytest
from sqlalchemy import select

from data_access_logic.entrypoint import UnknownRecordError
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
from data_access_logic.episode.commit_episode import CommitEpisode
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.meme.extractor import pending_sources, save_anti_memes, save_memes, unpaired_sources
from data_access_logic.flows import meme as meme_flow
from data_access_logic.meme.models import AntiDraft, AntiMeme, AntisDraft, MemeDraft
from db.schema import Episode, Meme, MemeCategory, get_env_session
from tool.test.mock_ai_client import MockAIClient


def test_commit_meme(shown):
    result = shown(CommitMeme(MemeCreateForm(
        text="約束は命より重い", category=MemeCategory.BELIEF)))

    assert (result["text"], result["category"]) == ("約束は命より重い", "信条")


def test_delete_meme(shown, world):
    other = shown(CommitMeme(MemeCreateForm(text="一緒に消える信条", category=MemeCategory.BELIEF)))

    result = shown(DeleteMeme(meme_ids=[world.meme_id, other["id"]]))

    assert result == [{"id": world.meme_id, "category": "信条", "anti_meme_id": None, "text": "テストの信条"},
                      {"id": other["id"], "category": "信条", "anti_meme_id": None, "text": "一緒に消える信条"}]


def test_delete_meme_deletes_its_anti_meme(shown, world, mock_ai):
    with get_env_session() as s, s.begin():
        save_anti_memes(s, [AntiMeme(id=world.meme_id, text="テストの信条の反転")])
        anti_id = s.get_one(Meme, world.meme_id).anti_meme_id

    result = shown(DeleteMeme(meme_ids=[world.meme_id]))

    assert [record["id"] for record in result] == [world.meme_id, anti_id]
    with get_env_session() as s:
        assert s.get(Meme, anti_id) is None


def test_delete_meme_keeps_all_when_one_is_missing(shown, world):
    with pytest.raises(UnknownRecordError):
        DeleteMeme(meme_ids=[world.meme_id, 10**9]).run()

    assert shown(DeleteMeme(meme_ids=[world.meme_id]))[0]["id"] == world.meme_id


def test_draw_memes(shown, world):
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
        id=world.meme_id, text="約束は守る", category=MemeCategory.LAW)))

    assert result == {"id": world.meme_id, "category": "理", "anti_meme_id": None, "text": "約束は守る"}


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
    UpdateMeme(MemeUpdateForm(id=world.meme_id, text="TODO: 言い回しを確かめる")).run()

    result = shown(ListPendingReviews())

    assert {"key", "kind", "title", "detail"} <= set(result[0])
    assert f"todo:meme:{world.meme_id}" in [item["key"] for item in result]


def test_meme_sources_are_episodes_not_ideas_or_characters(world):
    with get_env_session() as s:
        sources = {(source.table, source.id) for source in pending_sources(s)}

    assert ("episode", world.episode_id) in sources
    assert not {table for table, _ in sources} & {"idea", "character"}


def test_commit_episode_resets_meme_seeded(world):
    with get_env_session() as s, s.begin():
        s.get_one(Episode, world.episode_id).meme_seeded = True
    with get_env_session() as s, s.begin():
        CommitEpisode(EpisodeCommitForm(id=world.episode_id, main_text="市で二人が別れた。")).execute(s)

    with get_env_session() as s:
        assert s.get_one(Episode, world.episode_id).meme_seeded is False


def test_extracted_memes_are_saved_with_their_anti_memes(world):
    with get_env_session() as s, s.begin():
        added = save_memes(s, [MemeDraft(text="約束は命より重い", anti_text="命は約束より重い", category="信条")], [])
        meme = s.scalars(select(Meme).where(Meme.text == "約束は命より重い").order_by(Meme.id.desc())).first()
        assert meme is not None and meme.anti_meme_id is not None
        anti = s.get_one(Meme, meme.anti_meme_id)

        assert added == 2
        assert (anti.text, anti.category, anti.anti_meme_id) == ("命は約束より重い", "信条", meme.id)


class _AntiWritingAI(MockAIClient):
    """モックは配列を空で返すので、アンチミームだけは渡したミームの番号ごとに書く。"""

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort=""):
        if output is AntisDraft:
            memes = json.loads(prompt[:prompt.rindex("]") + 1])
            return AntisDraft(antis=[AntiDraft(number=item["番号"], anti_text=f"{item['ミーム']}の反転") for item in memes])
        return super().generate(prompt, output, system, timeout, tools, model, effort)


def test_extract_memes_pairs_unpaired_memes(world):
    meme_flow.refresh(_AntiWritingAI(seed=0))

    with get_env_session() as s:
        meme = s.get_one(Meme, world.meme_id)
        assert meme.anti_meme_id is not None
        anti = s.get_one(Meme, meme.anti_meme_id)
        assert (anti.text, anti.anti_meme_id, anti.category) == ("テストの信条の反転", meme.id, meme.category)
        assert not unpaired_sources(s)


def test_save_anti_memes_skips_paired_memes(world):
    with get_env_session() as s, s.begin():
        assert save_anti_memes(s, [AntiMeme(id=world.meme_id, text="一つ目")]) == 1
        assert save_anti_memes(s, [AntiMeme(id=world.meme_id, text="二つ目")]) == 0
