"""文体の好み(`data_access_logic/style_preference/`)と、AI が書くすべての文に書き方を足す `ai_client.generate`。"""
import json
from unittest import mock
from uuid import uuid4

from pydantic import BaseModel

from ai.claude_code import ai_client
from ai.instructions.style import EPISODE_STYLE_BASE, WRITING_STYLE_BASE
from data_access_logic.style_preference.commit_style_preference import CommitStylePreference
from data_access_logic.style_preference.extras import episode_style
from data_access_logic.style_preference.form import StylePreferenceCreateForm, StylePreferenceUpdateForm
from data_access_logic.style_preference.read_writing_style import ReadWritingStyle
from data_access_logic.style_preference.update_style_preference import UpdateStylePreference
from db.schema import StyleScope, get_env_session

# conftest がテストごとに `generate` をモックへ差し替えるので、差し替える前の本物を持っておく
_generate = ai_client.generate


def _rows(shown) -> tuple[str, str]:
    everywhere, episode_only = f"全体の好み {uuid4()}", f"本文の好み {uuid4()}"
    shown(CommitStylePreference(StylePreferenceCreateForm(text=everywhere, scope=StyleScope.ALL)))
    shown(CommitStylePreference(StylePreferenceCreateForm(text=episode_only)))
    return everywhere, episode_only


def test_commit_style_preference_defaults_to_episode(shown):
    result = shown(CommitStylePreference(StylePreferenceCreateForm(text=f"既定の好み {uuid4()}")))

    assert result["scope"] == "本文"


def test_update_style_preference_scope(shown):
    created = shown(CommitStylePreference(StylePreferenceCreateForm(text=f"直す好み {uuid4()}")))

    result = shown(UpdateStylePreference(StylePreferenceUpdateForm(id=created["id"], scope=StyleScope.ALL)))

    assert (result["text"], result["scope"]) == (created["text"], "全体")


def test_writing_style_has_only_rows_for_all_texts(shown):
    everywhere, episode_only = _rows(shown)

    text = shown(ReadWritingStyle())["text"]

    assert text.startswith(WRITING_STYLE_BASE)
    assert everywhere in text
    assert episode_only not in text
    assert EPISODE_STYLE_BASE not in text


def test_episode_style_adds_episode_rows_after_rows_for_all_texts(shown):
    everywhere, episode_only = _rows(shown)

    with get_env_session() as s:
        text = episode_style(s)

    assert text.startswith(WRITING_STYLE_BASE)
    assert text.index(everywhere) < text.index(EPISODE_STYLE_BASE) < text.index(episode_only)


class _Answer(BaseModel):
    answer: str


def test_generate_adds_writing_style_to_system(shown):
    everywhere, episode_only = _rows(shown)
    reply = ai_client._Reply(subtype="success", structured_output={"answer": "はい"})

    with mock.patch.object(ai_client, "_reply", return_value=reply) as replied:
        answer = _generate("問い", _Answer, system="生成ごとの指示")

    args = replied.call_args.args[1]
    system = args[args.index("--system-prompt") + 1]
    assert answer == _Answer(answer="はい")
    assert system.startswith("生成ごとの指示\n\n書く文の書き方:\n" + WRITING_STYLE_BASE)
    assert everywhere in system
    assert episode_only not in system
    assert json.loads(args[args.index("--json-schema") + 1]) == _Answer.model_json_schema()
