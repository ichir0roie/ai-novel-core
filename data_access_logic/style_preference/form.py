from data_access_logic.material import Form
from db.schema import StyleScope


class StylePreferenceCreateForm(Form):
    """範囲ごとに一行。その範囲の行が既にあれば、末尾に足す。空の文は、まだ書いていない範囲の行を置いておくのに使う。"""

    text: str
    scope: StyleScope = StyleScope.EPISODE


class StylePreferenceUpdateForm(Form):
    id: int
    text: str | None = None
    scope: StyleScope | None = None


class WritingStyleForm(Form):
    """書き方を読む所。`scope` は使う所の範囲(本文・プロットなど)で、全体の行 → その範囲の行の順に足す。
    本文の範囲だけは、全体の行 → 作品の指示(`story_id` の作品と、親をたどった祖先の作品) → 本文の行 → 推敲の行 → 話の指示の順に足す。"""

    scope: StyleScope = StyleScope.ALL
    story_id: int | None = None
    episode_id: int | None = None
