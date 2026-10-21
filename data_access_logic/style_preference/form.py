from pydantic import Field

from data_access_logic.material import Form
from db.schema import StyleScope


class StylePreferenceCreateForm(Form):
    """範囲ごとに一行。その範囲の行が既にあれば、末尾に足す。"""

    text: str = Field(min_length=1)
    scope: StyleScope = StyleScope.EPISODE


class StylePreferenceUpdateForm(Form):
    id: int
    text: str | None = Field(default=None, min_length=1)
    scope: StyleScope | None = None


class WritingStyleForm(Form):
    """書き方を読む所。`scope` は使う所の範囲(本文・プロットなど)で、全体の行 → 作品の指示 → その範囲の行 → 話の指示の順に足す。
    作品の指示は、`story_id` の作品と、親をたどった祖先の作品のものを足す。"""

    scope: StyleScope = StyleScope.ALL
    story_id: int | None = None
    episode_id: int | None = None
