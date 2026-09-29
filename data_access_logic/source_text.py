"""ミーム・出来事の種を抜き出す元の本文を扱う。"""
import re
from typing import Any, Generic, TypeVar

from pydantic import model_serializer

from data_access_logic.material import Material

_PLOT_SECTION = re.compile(r"^#[ \t]*plot[ \t]*\n(.*?)(?=^#[ \t]|\Z)", re.M | re.S)

Row = TypeVar("Row")


def plot_section(text: str | None) -> str:
    """人物の本文のうち `# plot` の節(その人物について進めたい筋書き)。"""
    match = _PLOT_SECTION.search(text or "")
    return match.group(1).strip() if match else ""


class SourceText(Material, Generic[Row]):
    # 抜き出したら印を付ける元の行
    row: Row
    # 何の本文か(アイデア・出来事など)
    label: str
    text: str


def batches(sources: list[SourceText[Row]], letters_limit: int) -> list[list[SourceText[Row]]]:
    """一度の呼び出しで渡す本文の字数が `letters_limit` を超えないよう分ける(一件で超えるものはそれだけで一束)。"""
    grouped: list[list[SourceText[Row]]] = []
    letters = 0
    for source in sources:
        if grouped and letters + len(source.text) <= letters_limit:
            grouped[-1].append(source)
            letters += len(source.text)
        else:
            grouped.append([source])
            letters = len(source.text)
    return grouped


class SourceBatch(Material, Generic[Row]):
    sources: list[SourceText[Row]]


class SourceBatchSerialized(SourceBatch[Any]):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> list[dict[str, Any]]:
        return [{"番号": number, "種類": source.label, "本文": source.text}
                for number, source in enumerate(self.sources, start=1)]
