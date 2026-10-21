"""文体の好み(`data_access_logic/style_preference/`)と、AI が書くすべての文に書き方を足す `ai_client.generate`。"""
import json
from unittest import mock
from uuid import uuid4

import pytest
from pydantic import BaseModel

from ai.claude_code import ai_client
from sqlalchemy import func, select

from data_access_logic.episode.commit_episode import CommitEpisode
from data_access_logic.episode.form import EpisodeCommitForm
from data_access_logic.story.commit_story import CommitStory
from data_access_logic.story.form import StoryCreateForm, StoryUpdateForm
from data_access_logic.story.update_story import UpdateStory
from data_access_logic.style_preference.commit_style_preference import CommitStylePreference
from data_access_logic.style_preference.extras import episode_style
from data_access_logic.style_preference.form import StylePreferenceCreateForm, StylePreferenceUpdateForm, WritingStyleForm
from data_access_logic.style_preference.read_writing_style import ReadWritingStyle
from data_access_logic.style_preference.update_style_preference import UpdateStylePreference
from db.schema import StylePreference, StyleScope, get_env_session
from db.style_defaults import DEFAULT_STYLE_PREFERENCES

# conftest がテストごとに `generate` をモックへ差し替えるので、差し替える前の本物を持っておく
_generate = ai_client.generate


def _text(name: str) -> str:
    return f"{name} {uuid4()}"


def _row(shown, name: str, scope: StyleScope) -> str:
    """範囲の行の末尾に足す(範囲ごとに一行)。"""
    text = _text(name)
    shown(CommitStylePreference(StylePreferenceCreateForm(text=text, scope=scope)))
    return text


def _story(shown, name: str, parent_story_id: int | None = None, instruction: str = "") -> int:
    return shown(CommitStory(StoryCreateForm(
        name=_text(name), parent_story_id=parent_story_id, instruction=instruction)))["id"]


def _story_instruction(shown, story_id: int, name: str) -> str:
    text = _text(name)
    shown(UpdateStory(StoryUpdateForm(id=story_id, instruction=text)))
    return text


def test_commit_style_preference_appends_to_the_row_of_its_scope(shown):
    first_text, second_text = _text("既定の好み"), _text("足した好み")
    first = shown(CommitStylePreference(StylePreferenceCreateForm(text=first_text)))
    second = shown(CommitStylePreference(StylePreferenceCreateForm(text=second_text)))

    assert first["scope"] == "本文"
    assert second["id"] == first["id"]
    assert second["text"].index(first_text) < second["text"].index(second_text)
    with get_env_session() as s:
        assert s.scalar(select(func.count()).select_from(StylePreference).where(StylePreference.scope == "本文")) == 1


def test_update_style_preference_refuses_scope_that_has_a_row(shown):
    episode_row = shown(CommitStylePreference(StylePreferenceCreateForm(text=_text("本文の好み"))))

    with pytest.raises(ValueError):
        shown(UpdateStylePreference(StylePreferenceUpdateForm(id=episode_row["id"], scope=StyleScope.ALL)))


def test_writing_style_adds_all_then_stories_then_scope_then_episode(shown, world):
    parent_story = world.story_id
    child_story = _story(shown, "子の作品", parent_story)
    other_story = _story(shown, "別の作品")
    everywhere = _row(shown, "全体の好み", StyleScope.ALL)
    plot_only = _row(shown, "プロットの好み", StyleScope.PLOT)
    episode_only = _row(shown, "本文の好み", StyleScope.EPISODE)
    in_child = _story_instruction(shown, child_story, "子の作品の指示")
    in_parent = _story_instruction(shown, parent_story, "親の作品の指示")
    in_other = _story_instruction(shown, other_story, "別の作品の指示")
    in_episode = _text("話の指示")
    shown(CommitEpisode(EpisodeCommitForm(id=world.episode_id, instruction=in_episode)))

    text = shown(ReadWritingStyle(WritingStyleForm(
        scope=StyleScope.PLOT, story_id=child_story, episode_id=world.episode_id)))["text"]

    assert text.index(everywhere) < text.index(in_parent) < text.index(in_child) < text.index(plot_only) < text.index(in_episode)
    assert episode_only not in text
    assert in_other not in text


def test_writing_style_without_story_has_neither_story_nor_narrow_texts(shown, world):
    in_story = _story_instruction(shown, world.story_id, "作品の指示")
    plot_only = _row(shown, "プロットの好み", StyleScope.PLOT)
    everywhere = _row(shown, "全体の好み", StyleScope.ALL)

    text = shown(ReadWritingStyle())["text"]

    assert everywhere in text
    assert in_story not in text
    assert plot_only not in text


def test_writing_style_has_default_rows_for_all_texts(shown):
    text = shown(ReadWritingStyle())["text"]

    for scope, default in DEFAULT_STYLE_PREFERENCES:
        assert (default.strip() in text) == (scope == StyleScope.ALL.value)


def test_episode_style_adds_episode_rows(shown, world):
    everywhere = _row(shown, "全体の好み", StyleScope.ALL)
    in_story = _story_instruction(shown, world.story_id, "作品の指示")
    episode_only = _row(shown, "本文の好み", StyleScope.EPISODE)
    plot_only = _row(shown, "プロットの好み", StyleScope.PLOT)

    with get_env_session() as s:
        text = episode_style(s, world.story_id)

    assert text.index(everywhere) < text.index(in_story) < text.index(episode_only)
    assert plot_only not in text
    assert "◇" not in text
    for scope, default in DEFAULT_STYLE_PREFERENCES:
        assert default.strip() in text


class _Answer(BaseModel):
    answer: str


def test_generate_adds_writing_style_of_scope_and_story_to_system(shown, world):
    everywhere = _row(shown, "全体の好み", StyleScope.ALL)
    in_story = _story_instruction(shown, world.story_id, "作品の指示")
    plot_only = _row(shown, "プロットの好み", StyleScope.PLOT)
    episode_only = _row(shown, "本文の好み", StyleScope.EPISODE)
    reply = ai_client._Reply(subtype="success", structured_output={"answer": "はい"})

    with mock.patch.object(ai_client, "_reply", return_value=reply) as replied:
        answer = _generate("問い", _Answer, system="生成ごとの指示", style_scope=StyleScope.PLOT, story_id=world.story_id)

    args = replied.call_args.args[1]
    system = args[args.index("--system-prompt") + 1]
    assert answer == _Answer(answer="はい")
    assert system.startswith("生成ごとの指示\n\n書く文の書き方:\n")
    assert system.index(everywhere) < system.index(in_story) < system.index(plot_only)
    assert episode_only not in system
    assert json.loads(args[args.index("--json-schema") + 1]) == _Answer.model_json_schema()
