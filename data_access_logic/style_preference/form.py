from pydantic import Field, model_validator

from data_access_logic.material import Form
from db.schema import StyleScope


def check_scope_story(scope: StyleScope, story_id: int | None) -> None:
    if scope == StyleScope.STORY and story_id is None:
        raise ValueError(f"範囲が{StyleScope.STORY.value}の行には、効く作品(story_id)を入れる")
    if scope != StyleScope.STORY and story_id is not None:
        raise ValueError(f"story_id を入れられるのは、範囲が{StyleScope.STORY.value}の行だけ")


class StylePreferenceCreateForm(Form):
    text: str = Field(min_length=1)
    scope: StyleScope = StyleScope.EPISODE
    story_id: int | None = None

    @model_validator(mode="after")
    def _check(self) -> "StylePreferenceCreateForm":
        check_scope_story(self.scope, self.story_id)
        return self


class StylePreferenceUpdateForm(Form):
    id: int
    text: str | None = Field(default=None, min_length=1)
    scope: StyleScope | None = None
    story_id: int | None = None


class WritingStyleForm(Form):
    """書き方を読む所。`scope` は使う所の範囲(本文・プロットなど)で、全体 → ストーリー → その範囲の順に足す。
    ストーリーの行は、`story_id` の作品と、親をたどった祖先の作品の行だけを足す。"""

    scope: StyleScope = StyleScope.ALL
    story_id: int | None = None
