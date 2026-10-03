"""ミーム・出来事の種を抜き出す元の本文を扱う。"""
import re
from typing import Any, Protocol

from pydantic import model_serializer
from sqlalchemy.orm import Session

from data_access_logic.material import Material
from db.schema import Base

# 検証結果は本文の末尾にこの見出しの節として持つ(別の列は持たない)。空ならまだ検めていない。
FACT_CHECK_HEADING = "# 検証結果"
_FACT_CHECK_SECTION = re.compile(r"\n*^#[ \t]*検証結果[ \t]*\n.*\Z", re.M | re.S)


def strip_fact_check(text: str | None) -> str:
    """本文から検証結果の節を取り除いた、素の本文を返す。"""
    return _FACT_CHECK_SECTION.sub("", text or "").rstrip()


class SourceText(Material):
    # 抜き出したら印を付ける元の行(API で運べるよう、行そのものではなく表と id で指す)
    table: str
    id: int
    # 何の本文か(アイデア・出来事など)
    label: str
    text: str


def source_of(row: Base, label: str, text: str) -> SourceText:
    return SourceText(table=row.__tablename__, id=row.id, label=label, text=text)


def row_of(s: Session, table: str, id_: int) -> Any:
    model = next(mapper.class_ for mapper in Base.registry.mappers if mapper.class_.__tablename__ == table)
    return s.get_one(model, id_)


class _Text(Protocol):
    text: str


def batches[T: _Text](sources: list[T], letters_limit: int) -> list[list[T]]:
    """一度の呼び出しで渡す本文の字数が `letters_limit` を超えないよう分ける(一件で超えるものはそれだけで一束)。"""
    grouped: list[list[T]] = []
    letters = 0
    for source in sources:
        if grouped and letters + len(source.text) <= letters_limit:
            grouped[-1].append(source)
            letters += len(source.text)
        else:
            grouped.append([source])
            letters = len(source.text)
    return grouped


class SourceBatch(Material):
    sources: list[SourceText]


class SourceBatchSerialized(SourceBatch):
    """ai プロンプトが理解しやすい形に整形したレスポンスを行う。"""

    @model_serializer
    def _for_prompt(self) -> list[dict[str, Any]]:
        return [{"番号": number, "種類": source.label, "本文": source.text}
                for number, source in enumerate(self.sources, start=1)]
