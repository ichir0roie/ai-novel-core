import pytest

from ai.claude_code import story_writer
from ai.time_keeper import episode_summary
from data_access_logic.query import common_query
from db.schema import Plot, EpisodeSummary, Episode, Location, Story, summary_source_hash
from db.stamp import Stamp


@pytest.fixture
def story(session):
    place = Location(name="村", kind="村", text="")
    session.add(place)
    session.flush()
    record = Story(name="村の話", place_id=place.id, text="筋書き", narration="三人称",
                   state="執筆中", start=Stamp(2100, 4, 1), end=Stamp(2300))
    session.add(record)
    session.commit()
    return record


def add_plots(session, story, count):
    for number in range(1, count + 1):
        session.add(Plot(story_id=story.id, start=Stamp(2100, 4, number), title=f"第{number}話",
                            synced=True, episode=Episode(text=f"{number}話の本文")))
    session.commit()


def last_plot(session, story):
    return session.scalars(common_query.story_plots_select(story.id)).all()[-1]


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    def fake(prompt, schema, *, system=None, timeout=None, options=None, **_):
        recorded.append({"prompt": prompt, "schema": schema, "system": system})
        if schema is episode_summary._SCHEMA:
            return {"summary": "二人が村を出た", "style": "短い地の文と会話"}
        return {"title": "題", "text": "本文"}

    monkeypatch.setattr(story_writer.ai_client, "try_generate_json", fake)
    return recorded


def test_recap_reads_only_the_last_three_plots_one_by_one(session, story, calls):
    add_plots(session, story, 4)

    story_writer.write_next_episode(session, story.id)

    recaps = [call for call in calls if call["schema"] is episode_summary._SCHEMA]
    assert len(recaps) == 3
    for recap, number in zip(recaps, (2, 3, 4)):
        assert f"{number}話の本文" in recap["prompt"]
    assert all("1話の本文" not in call["prompt"] for call in calls)


def test_plot_prompt_passes_summaries_instead_of_texts(session, story, calls):
    add_plots(session, story, 2)

    record = story_writer.write_next_episode(session, story.id)

    plot_prompt = calls[-1]["prompt"]
    assert "1話の本文" not in plot_prompt and "2話の本文" not in plot_prompt
    assert plot_prompt.count('"summary": "二人が村を出た"') == 2
    assert '"title": "第1話"' in plot_prompt and '"title": "第2話"' in plot_prompt
    assert "直前の話の文体(これに揃える): 短い地の文と会話" in plot_prompt
    assert last_plot(session, story).id == record.id


def test_only_episode_uses_fable_high(session, story, monkeypatch):
    add_plots(session, story, 1)
    used = []

    def fake(prompt, schema, *, model=None, effort=None, **_):
        used.append((schema, model, effort))
        if schema is episode_summary._SCHEMA:
            return {"summary": "", "style": ""}
        return {"title": "題", "text": "本文"}

    monkeypatch.setattr(story_writer.ai_client, "try_generate_json", fake)

    story_writer.write_next_episode(session, story.id)

    assert used[-1] == (story_writer._SCHEMA, "claude-fable-5-1", "high")
    assert all((model, effort) == (None, None) for _, model, effort in used[:-1])


def test_written_plot_is_laid_out(session, story, monkeypatch):
    monkeypatch.setattr(story_writer.ai_client, "try_generate_json",
                        lambda *a, **k: {"title": "題", "text": "朝が来た。窓が白い。\n◇\n夜。"})

    record = story_writer.write_next_episode(session, story.id)

    assert record.body == "朝が来た。\n窓が白い。\n\n\n夜。"
    assert record.episode.letters == len(record.body)
    assert (record.episode.model, record.episode.effort) == ("claude-fable-5-1", "high")


def test_recap_is_kept_in_the_episode_summary_table(session, story, calls):
    add_plots(session, story, 2)

    story_writer.write_next_episode(session, story.id)

    rows = session.query(EpisodeSummary).order_by(EpisodeSummary.episode_id).all()
    assert [(row.story_id, row.summary, row.style) for row in rows] == [
        (story.id, "二人が村を出た", "短い地の文と会話")] * 2
    assert rows[0].source_hash == summary_source_hash("1話の本文")


def test_recap_is_reused_while_the_episode_is_unchanged(session, story, calls):
    add_plots(session, story, 2)
    story_writer.write_next_episode(session, story.id)
    calls.clear()

    story_writer.write_next_episode(session, story.id)

    recaps = [call for call in calls if call["schema"] is episode_summary._SCHEMA]
    assert len(recaps) == 1
    assert "本文" in recaps[0]["prompt"] and "2話の本文" not in recaps[0]["prompt"]


def test_recap_is_rewritten_when_the_episode_changes(session, story, calls):
    add_plots(session, story, 2)
    third = story_writer.write_next_episode(session, story.id)
    plot = session.query(Plot).filter_by(story_id=story.id, title="第2話").one()
    plot.episode.text = "2話の書き直した本文"
    session.commit()
    calls.clear()

    story_writer.write_next_episode(session, story.id, plot_id=third.id)

    recaps = [call for call in calls if call["schema"] is episode_summary._SCHEMA]
    assert len(recaps) == 1 and "2話の書き直した本文" in recaps[0]["prompt"]
    row = session.query(EpisodeSummary).filter_by(episode_id=plot.episode.id).one()
    assert row.source_hash == summary_source_hash("2話の書き直した本文")


def test_first_plot_skips_the_recap(session, story, calls):
    record = story_writer.write_next_episode(session, story.id)

    assert len(calls) == 1
    assert calls[0]["schema"] is story_writer._SCHEMA
    assert (record.title, record.start) == ("題", None)


def test_texts_are_passed_when_no_recap_is_written(session, story, monkeypatch):
    add_plots(session, story, 2)
    prompts = []

    def fake(prompt, schema, *, system=None, timeout=None, options=None, **_):
        prompts.append(prompt)
        if schema is episode_summary._SCHEMA:
            return {}
        return {"title": "題", "text": "本文"}

    monkeypatch.setattr(story_writer.ai_client, "try_generate_json", fake)

    record = story_writer.write_next_episode(session, story.id)

    assert "1話の本文" in prompts[-1] and "2話の本文" in prompts[-1]
    assert '"summary"' not in prompts[-1]
    assert "直前の話の文体" not in prompts[-1]
    assert session.query(EpisodeSummary).count() == 0
    assert record.body == "本文"


def test_system_prompt_tells_to_follow_the_recap():
    assert "概要の筋をそのまま受け継ぎ" in story_writer._SYSTEM_PROMPT


def test_seeded_plot_is_filled_in_place(session, story, calls):
    add_plots(session, story, 2)
    seeded = Plot(story_id=story.id, start=Stamp(2100, 4, 3), title="堕ちる翼",
                     key="## 場面\n1. 面会室 / ミレア",
                     viewpoint="ミレア", place="エンピレオ", synced=False)
    session.add(seeded)
    session.commit()

    record = story_writer.write_next_episode(session, story.id)

    assert record.id == seeded.id
    assert record.body == "本文"
    assert record.key == "## 場面\n1. 面会室 / ミレア"
    prompt = calls[-1]["prompt"]
    assert "この話の種" in prompt and "面会室 / ミレア" in prompt
    assert "視点と場所: ミレア / エンピレオ" in prompt


def test_plot_id_picks_the_plot_to_write(session, story, calls):
    add_plots(session, story, 1)
    seeds = [Plot(story_id=story.id, start=Stamp(2100, 4, number), title="", key=f"種{number}",
                     synced=False) for number in (2, 3)]
    session.add_all(seeds)
    session.commit()

    record = story_writer.write_next_episode(session, story.id, plot_id=seeds[1].id)

    assert record.id == seeds[1].id
    assert "種3" in calls[-1]["prompt"]


def test_seeded_later_plots_do_not_block_writing(session, story, calls):
    add_plots(session, story, 1)
    session.add(Plot(story_id=story.id, start=Stamp(2100, 4, 9), title="", key="先の種",
                        synced=False))
    session.commit()

    assert story_writer.write_next_episode(session, story.id) is not None


def test_unsynced_written_plot_blocks_writing(session, story, calls):
    add_plots(session, story, 2)
    session.add(Plot(story_id=story.id, start=Stamp(2100, 4, 3), title="", key="",
                        synced=False, episode=Episode(text="書いた本文")))
    session.commit()

    assert story_writer.write_next_episode(session, story.id) is None


def test_previous_plots_are_taken_from_before_the_target(session, story, calls):
    add_plots(session, story, 2)
    seed = Plot(story_id=story.id, start=Stamp(2100, 4, 3), title="", key="種",
                   synced=False)
    session.add_all([seed, Plot(story_id=story.id, start=Stamp(2100, 4, 7), title="先の話", key="",
                                   synced=True, episode=Episode(text="7話の本文"))])
    session.commit()

    story_writer.write_next_episode(session, story.id, plot_id=seed.id)

    assert "7話の本文" not in calls[0]["prompt"]


def test_system_prompt_states_the_length_target():
    assert "一話は5000〜8000字" in story_writer._SYSTEM_PROMPT
    assert "場面" in story_writer._SYSTEM_PROMPT


def test_style_extras_from_the_caller_reach_the_system_prompt(session, story, calls):
    """世界の舞台設定・既存の話から抽出した文体の癖は、コアに定数で持たず、呼び出し側から渡す。"""
    story_writer.write_next_episode(session, story.id,
                                    shared_style_extra="西暦一万年のSF世界", style_extra="この世界の文体の癖")

    system = calls[-1]["system"]
    assert "西暦一万年のSF世界" in system and "この世界の文体の癖" in system
    assert system != story_writer._SYSTEM_PROMPT
