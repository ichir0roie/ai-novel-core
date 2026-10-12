from typing import Literal

from pydantic import Field

from data_access_logic.material import Form

Stance = Literal["感想", "同意", "反対", "修正案"]


class ReactionForm(Form):
    """語り部・人物役が本文の差分に返す反応。"""

    # 読んだ差分のうち一番新しいもの。いくつか溜まっていたら、まとめて読んで一つ返す
    diff_id: int
    # 空なら語り部
    character_id: int | None = None
    stance: Stance
    # 反応する本文の箇所。本文からそのまま引く(画面がその箇所へ飛ぶのに使う)
    quote: str | None = None
    text: str = Field(min_length=1)
