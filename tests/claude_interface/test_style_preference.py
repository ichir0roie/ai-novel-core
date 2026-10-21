"""文体の好み(`data_access_logic/style_preference/`)と、AI が書くすべての文に書き方を足す `ai_client.generate`。"""
import json
from unittest import mock
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from ai.claude_code import ai_client
from ai.instructions.style import EPISODE_LAYOUT_INSTRUCTION
from data_access_logic.entrypoint import UnknownRecordError
from data_access_logic.story.commit_story import CommitStory
from data_access_logic.story.form import StoryCreateForm
from data_access_logic.style_preference.commit_style_preference import CommitStylePreference
from data_access_logic.style_preference.extras import episode_style, scopes_for
from data_access_logic.style_preference.form import StylePreferenceCreateForm, StylePreferenceUpdateForm, WritingStyleForm
from data_access_logic.style_preference.read_writing_style import ReadWritingStyle
from data_access_logic.style_preference.update_style_preference import UpdateStylePreference
from db.schema import StyleScope, get_env_session
from db.style_defaults import DEFAULT_STYLE_PREFERENCES

# conftest がテストごとに `generate` をモックへ差し替えるので、差し替える前の本物を持っておく
_generate = ai_client.generate


def _text(name: str) -> str:
    return f"{name} {uuid4()}"


def _row(shown, name: str, scope: StyleScope, story_id: int | None = None) -> str:
    text = _text(name)
    shown(CommitStylePreference(StylePreferenceCreateForm(text=text, scope=scope, story_id=story_id)))
    return text


def _story(shown, name: str, parent_story_id: int | None = None) -> int:
    return shown(CommitStory(StoryCreateForm(name=_text(name), parent_story_id=parent_story_id)))["id"]


def test_scopes_for_goes_from_wide_to_narrow():
    assert scopes_for(StyleScope.ALL) == (StyleScope.ALL,)
    assert scopes_for(StyleScope.STORY) == (StyleScope.ALL, StyleScope.STORY)
    assert scopes_for(StyleScope.PLOT) == (StyleScope.ALL, StyleScope.STORY, StyleScope.PLOT)
    assert scopes_for(StyleScope.EPISODE) == (StyleScope.ALL, StyleScope.STORY, StyleScope.EPISODE)


def test_commit_style_preference_defaults_to_episode(shown):
    result = shown(CommitStylePreference(StylePreferenceCreateForm(text=_text("既定の好み"))))

    assert (result["scope"], result["story_id"]) == ("本文", None)


def test_story_row_needs_story_and_other_rows_do_not_take_one(world):
    with pytest.raises(ValidationError):
        StylePreferenceCreateForm(text="作品の指定が無い", scope=StyleScope.STORY)
    with pytest.raises(ValidationError):
        StylePreferenceCreateForm(text="作品を指定した本文の行", scope=StyleScope.EPISODE, story_id=world.story_id)


def test_commit_style_preference_checks_story_exists(shown):
    with pytest.raises(UnknownRecordError):
        shown(CommitStylePreference(StylePreferenceCreateForm(
            text=_text("無い作品"), scope=StyleScope.STORY, story_id=2_000_000_000)))


def test_update_style_preference_scope(shown, world):
    created = shown(CommitStylePreference(StylePreferenceCreateForm(text=_text("直す好み"))))

    to_all = shown(UpdateStylePreference(StylePreferenceUpdateForm(id=created["id"], scope=StyleScope.ALL)))
    with pytest.raises(ValueError):
        shown(UpdateStylePreference(StylePreferenceUpdateForm(id=created["id"], scope=StyleScope.STORY)))
    to_story = shown(UpdateStylePreference(StylePreferenceUpdateForm(
        id=created["id"], scope=StyleScope.STORY, story_id=world.story_id)))

    assert (to_all["text"], to_all["scope"]) == (created["text"], "全体")
    assert (to_story["scope"], to_story["story_id"]) == ("ストーリー", world.story_id)


def test_writing_style_adds_wide_rows_then_narrow_rows(shown, world):
    parent_story = world.story_id
    child_story = _story(shown, "子の作品", parent_story)
    other_story = _story(shown, "別の作品")
    everywhere = _row(shown, "全体の好み", StyleScope.ALL)
    plot_only = _row(shown, "プロットの好み", StyleScope.PLOT)
    episode_only = _row(shown, "本文の好み", StyleScope.EPISODE)
    # 子の作品の行を先に足しても、祖先の作品の行が先に並ぶ
    in_child = _row(shown, "子の作品の好み", StyleScope.STORY, child_story)
    in_parent = _row(shown, "親の作品の好み", StyleScope.STORY, parent_story)
    in_other = _row(shown, "別の作品の好み", StyleScope.STORY, other_story)

    text = shown(ReadWritingStyle(WritingStyleForm(scope=StyleScope.PLOT, story_id=child_story)))["text"]

    assert text.index(everywhere) < text.index(in_parent) < text.index(in_child) < text.index(plot_only)
    assert episode_only not in text
    assert in_other not in text


def test_writing_style_for_parent_story_has_no_child_story_rows(shown, world):
    child_story = _story(shown, "子の作品", world.story_id)
    in_child = _row(shown, "子の作品の好み", StyleScope.STORY, child_story)
    in_parent = _row(shown, "親の作品の好み", StyleScope.STORY, world.story_id)

    text = shown(ReadWritingStyle(WritingStyleForm(scope=StyleScope.EPISODE, story_id=world.story_id)))["text"]

    assert in_parent in text
    assert in_child not in text


def test_writing_style_without_story_has_neither_story_rows_nor_narrow_rows(shown, world):
    in_story = _row(shown, "作品の好み", StyleScope.STORY, world.story_id)
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


def test_episode_style_adds_episode_rows_then_layout(shown, world):
    everywhere = _row(shown, "全体の好み", StyleScope.ALL)
    in_story = _row(shown, "作品の好み", StyleScope.STORY, world.story_id)
    episode_only = _row(shown, "本文の好み", StyleScope.EPISODE)
    plot_only = _row(shown, "プロットの好み", StyleScope.PLOT)

    with get_env_session() as s:
        text = episode_style(s, world.story_id)

    assert text.index(everywhere) < text.index(in_story) < text.index(episode_only) < text.index(EPISODE_LAYOUT_INSTRUCTION)
    assert text.endswith(EPISODE_LAYOUT_INSTRUCTION)
    assert plot_only not in text
    for scope, default in DEFAULT_STYLE_PREFERENCES:
        assert default.strip() in text


class _Answer(BaseModel):
    answer: str


def test_generate_adds_writing_style_of_scope_and_story_to_system(shown, world):
    everywhere = _row(shown, "全体の好み", StyleScope.ALL)
    in_story = _row(shown, "作品の好み", StyleScope.STORY, world.story_id)
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
