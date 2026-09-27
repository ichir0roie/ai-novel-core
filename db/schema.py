#!/usr/bin/env python3
from __future__ import annotations

import enum
import hashlib
import os
import re
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, Integer, String, DECIMAL, JSON, TypeDecorator,
    create_engine,
    ForeignKey,
    UniqueConstraint,
    select,
    Select,
    text,
    update,
    or_,
    and_,
    delete,
)
from sqlalchemy.orm import (
    Session,
    joinedload,
    selectinload,
    lazyload,
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    validates,
)

from sqlalchemy import func

from db.polygon import parse_polygon
from db.stamp import Stamp


class StampType(TypeDecorator):

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        parsed = Stamp.parse(value)
        if parsed is None:
            raise ValueError(f"Invalid stamp value: {value}")
        return parsed.to_int()

    def process_result_value(self, value, dialect):
        return Stamp.from_int(value)


class PolygonType(TypeDecorator):

    impl = JSON
    cache_ok = True

    def __init__(self):
        # 既定だと None が JSON の 'null' 文字列で入り、IS NULL で引けなくなる
        super().__init__(none_as_null=True)

    def process_bind_param(self, value, dialect):
        return parse_polygon(value)


LOCATION_COLUMNS = ("location_world", "location_planet",
                    "location_longitude", "location_latitude",
                    "location_altitude")

_LOCATION_TAGS = ("w", "p", "lon", "lat", "alt")


def _digit(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value).strip()
    return str(int(number)) if number == int(number) else repr(number)


def location_text(values) -> str | None:
    """`w4/p1/lon12/lat-/alt-` のように、上から順に並ぶ。前方一致がそのまま
    「同じ世界線」「同じ星」の絞り込みになる。
    """
    get = values.get if hasattr(values, "get") else (
        lambda column: getattr(values, column, None))
    parts = [get(column) for column in LOCATION_COLUMNS]
    if all(part in (None, "") for part in parts):
        return None
    return "/".join(
        tag + ("-" if part in (None, "") else _digit(part))
        for tag, part in zip(_LOCATION_TAGS, parts))


class Base(DeclarativeBase):

    # SQLite は「INTEGER PRIMARY KEY」だけを rowid の別名として autoincrement する。
    # Integer だと型名が INTEGER と一致せず insert のたびに id が NULL のまま失敗する。
    # sort_order は列の並び順を明示するための番号。継承の段が一段深くなるごとに
    # 開始値を 100 増やし、同じクラス内では 10 刻みで振る(あとで列を挟みやすい)。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, sort_order=0)


# 自分のディレクトリに置く md の名前の頭。子の md の名前は親の id(1 から)で始まるので、
# ASCII 順でも数の順でも、ディレクトリの中の先頭に並ぶ
RECORD_PREFIX = "0_"


class MarkdownBase(Base):
    __abstract__ = True

    # md 側で `# <名前>` の節として出し入れする列。`# data` には出さない
    TEXT_SECTIONS: tuple[str, ...] = ("text",)
    # `# data` に子の行の配列として出し入れする relationship の名前
    CHILD_LISTS: tuple[str, ...] = ()
    # md 名の既定にする列。`# data` の無い手書きの md では、この列を md 名から埋める
    NAME_COLUMN: str | None = None
    # 持つテーブルの md は、md 名(拡張子を除く)のディレクトリを作り、その中に `record_name` で置く
    MARKDOWN_OWN_DIRECTORY: bool = False
    # 親の行を指す relationship の名前。持つテーブルの md は、`worlds/{table}/` ではなく
    # 親の md と同じディレクトリ(親は `MARKDOWN_OWN_DIRECTORY` を持つ)に並べる
    MARKDOWN_PARENT: str | None = None
    # 持つテーブルは md の代わりに、親の md と同じ名前で拡張子だけをこれにしたファイルを親の隣に置く。
    # 親一行につき一行で、`# data` も見出しも無い本文(text)だけで出し入れする
    BODY_FILE_EXTENSION: str | None = None

    text: Mapped[str] = mapped_column(String,  nullable=False, sort_order=10000)

    directory_path: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None, sort_order=20000,
        comment="import,export時の配置先。worlds/{table}/ からの相対ディレクトリパス。"
                "空ならテーブル直下に置く")
    filename: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None, sort_order=20010,
        comment="import,export時のファイル名(id・拡張子を除いた部分)。"
                "空なら {id}.md。テーブルが持つ name 等の列とは別物")

    def default_filename(self) -> str | None:
        return getattr(self, self.NAME_COLUMN) if self.NAME_COLUMN else None

    @property
    def markdown_name(self) -> str:
        name = self.filename or self.default_filename()
        return f"{self.id}_{name.replace('/', '／')}.md" if name else f"{self.id}.md"

    @property
    def record_name(self) -> str:
        """自分のディレクトリに置くときの md 名。id はディレクトリの名前が持つ"""
        _, _, name = self.markdown_name[: -len(".md")].partition("_")
        return f"{RECORD_PREFIX}{name}.md"

    @classmethod
    def parse_markdown_stem(cls, stem: str) -> tuple[int | None, dict]:
        id_part, _, filename_part = stem.partition("_")
        row_id, filename = (int(id_part), filename_part or None) if id_part.isdigit() else (None, stem)
        values = {"filename": filename}
        if cls.NAME_COLUMN and filename:
            values[cls.NAME_COLUMN] = filename
        return row_id, values


class Location(MarkdownBase):

    __tablename__ = "location"

    name: Mapped[str | None] = mapped_column(String, sort_order=200)
    kind: Mapped[str | None] = mapped_column(String, sort_order=210)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("location.id"), sort_order=220)

    # 位置は**一つの座標系だけ**で持つ。経度・緯度・高度で持ち、
    # **どこを原点とするかは星ごとに決めて、その星の md に書く**。
    location_world: Mapped[float | None] = mapped_column(DECIMAL, comment="世界線番号 W", sort_order=230)
    location_planet: Mapped[int | None] = mapped_column(Integer, comment="惑星番号 P", sort_order=240)
    location_longitude: Mapped[float | None] = mapped_column(DECIMAL, comment="経度。基準の子午線から東へ何度(西は負)", sort_order=250)
    location_latitude: Mapped[float | None] = mapped_column(DECIMAL, comment="緯度。赤道から北へ何度(南は負)", sort_order=260)
    location_altitude: Mapped[float | None] = mapped_column(DECIMAL, comment="高度。基準面から上へ何 m", sort_order=270)
    polygon: Mapped[dict | None] = mapped_column(
        PolygonType, comment="輪郭。GeoJSON の Polygon(`coordinates` は [経度, 緯度] の環の並び、"
        "先頭が外周で以降は穴)。地図では面として描く。経緯度が無くても持てる", sort_order=280)

    area: Mapped[float | None] = mapped_column(
        DECIMAL, comment="広さ。単位は決めていないが、親と子で揃える。"
        "子の広さは親未満、兄弟(同じ parent_id)を足しても親を超えない", sort_order=290)
    environment: Mapped[str | None] = mapped_column(String, comment="環境", sort_order=300)

    sample_region: Mapped[str | None] = mapped_column(
        String, comment="参考にした実在の地域(例: 「北欧」「地中海沿岸」)。"
        "固有名詞をそのまま使うのではなく、地理・気候・景観の手がかりとして持つ", sort_order=305)
    sample_culture: Mapped[str | None] = mapped_column(
        String, comment="参考にした実在の文化(例: 「遊牧」「稲作」)。"
        "風習・生活様式・価値観の手がかりとして持つ", sort_order=307)
    sample_era: Mapped[str | None] = mapped_column(
        String, comment="参考にした実在の時代(例: 「中世」「産業革命期」)。"
        "技術水準・社会制度の手がかりとして持つ", sort_order=308)

    start: Mapped[Stamp | None] = mapped_column(StampType, sort_order=310)
    end: Mapped[Stamp | None] = mapped_column(StampType, sort_order=320)

    active_random_generation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 自分の親(一つ上の場所)。木をのぼって道筋(place_path)を組むのに使う。
    # 書き込みは常に parent_id を直に触るので、どちらも読み取り専用にしておく
    # (viewonly を外すと、同じ外部キーを double-write しようとして SQLAlchemy が警告する)。
    parent: Mapped["Location | None"] = relationship(
        remote_side="Location.id", viewonly=True, lazy="noload")
    children: Mapped[list[Location]] = relationship(viewonly=True)

    NAME_COLUMN = "name"


class EventSeededMixin:
    event_seeded: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="出来事の種を抜き出し済みか。false に戻すと、次の毎日のルーチンで抜き出し直す",
        sort_order=9000)


class MemeSeededMixin:
    meme_seeded: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="ミームを抜き出し済みか。false に戻すと、次の抽出で抜き出し直す",
        sort_order=9010)


class FactCheckMixin:
    TEXT_SECTIONS = ("text", "fact_check")

    fact_check: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="AI が Dラボ・ネット検索で検めた妥当性と補足。空ならまだ検めていない",
        sort_order=10010)


class Event(EventSeededMixin, MemeSeededMixin, MarkdownBase):

    __tablename__ = "event"

    name: Mapped[str] = mapped_column(String, sort_order=200)
    # 断面(ReadBrief)に出すかどうかだけを持つ。分類は name/text の書き方で表す。
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, sort_order=210)
    time: Mapped[Stamp] = mapped_column(StampType, index=True, sort_order=220)

    parent_event_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("event.id"), sort_order=230)

    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"), index=True, sort_order=240)
    location: Mapped[Location | None] = relationship(lazy="noload")

    # 行動もここに入る(人物の行動に別表は無い)。誰の行動かは
    # event_character(中間テーブル、多対多)が持つ。空なら
    # 誰の行動でもない「ただ起きたこと」。
    event_characters: Mapped[list["EventCharacter"]] = relationship(
        back_populates="event", lazy="noload", cascade="all, delete-orphan")

    start: Mapped[Stamp | None] = mapped_column(StampType, sort_order=250)
    end: Mapped[Stamp | None] = mapped_column(StampType, sort_order=260)

    parent_event: Mapped["Event | None"] = relationship(
        remote_side="Event.id", back_populates="child_events", lazy="noload"
    )
    child_events: Mapped[list["Event"]] = relationship(
        back_populates="parent_event", lazy="noload", cascade="all, delete-orphan"
    )


class EventCharacter(Base):
    __tablename__ = "event_character"

    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("event.id"), index=True, sort_order=100)
    character_id: Mapped[int] = mapped_column(Integer, ForeignKey("character.id"), index=True, sort_order=110)

    event: Mapped["Event"] = relationship(back_populates="event_characters", lazy="noload")
    character: Mapped["Character"] = relationship(lazy="noload")


def summary_source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EventSummary(Base):
    __tablename__ = "event_summary"

    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("event.id"), unique=True, index=True, sort_order=100)
    source_hash: Mapped[str] = mapped_column(
        String, comment="要約した本文の sha256。本文と食い違ったら作り直す", sort_order=110)
    text: Mapped[str] = mapped_column(String, comment="要約", sort_order=120)


class EventSeed(Base):
    __tablename__ = "event_seed"

    text: Mapped[str] = mapped_column(String, comment="種", sort_order=100)
    consolidated: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="棚卸し(似た種をまとめる)を済ませたか。新しい種は false", sort_order=110)


class MemeCategory(enum.StrEnum):
    BELIEF = "信条"
    DESIRE = "欲求"
    SITUATION = "境遇"
    GROUP = "集団"
    LAW = "理"


MEME_CATEGORIES = tuple(category.value for category in MemeCategory)


class Meme(FactCheckMixin, MarkdownBase):
    """ミームは移り変わり・伝染していくものなので、どの元から抜き出したか、どの人物が持つかは持たない
    (元の側の `meme_seeded` で、抜き出し済みかだけを管理する)。
    """

    __tablename__ = "meme"

    category: Mapped[str | None] = mapped_column(
        String, nullable=True,
        comment=f"分類。{'/'.join(MEME_CATEGORIES)} のいずれか。空なら次の抽出で AI が振る",
        sort_order=200)


class Oracle(FactCheckMixin, MemeSeededMixin, MarkdownBase):
    """著者自身の創作・AI についての覚え書き。物語のデータではない。"""

    __tablename__ = "oracle"


CHARACTER_KIND_PERSON = "人物"


class PersonalityLevel(enum.StrEnum):
    NONE = "無"
    LOW = "低"
    NORMAL = "並"
    HIGH = "高"
    MUST = "必"


PERSONALITY_LEVELS = tuple(level.value for level in PersonalityLevel)
PERSONALITY_DEFAULT = PersonalityLevel.NORMAL.value

PERSONALITY_COLUMNS = (
    "sincerity", "curiosity", "proactivity", "cooperativeness", "sociability",
    "emotional_expression", "self_esteem", "self_efficacy", "stress_resilience",
    "flexibility_of_values", "sensitivity", "imagination",
)


PERSON_PARAMETER_COLUMNS = (
    "family_name", "sex", "height", "build", "first_person", "second_person", "third_person", "tone", "dialect",
)
PARAMETER_COLUMNS = (*PERSON_PARAMETER_COLUMNS, *PERSONALITY_COLUMNS)


def check_personality(data) -> None:
    """空(None)は「この期間では決めない」として通す。"""
    bad = {column: data[column] for column in PERSONALITY_COLUMNS
           if data.get(column) is not None and data[column] not in PERSONALITY_LEVELS}
    if bad:
        raise ValueError(
            f"性格は {'/'.join(PERSONALITY_LEVELS)} のいずれか: {bad}")


class Character(EventSeededMixin, MemeSeededMixin, MarkdownBase):
    """人物に限らず、国・組織・集団・物も一行として持つ(`kind` で区別)。

    ミームは人物どうしで移り変わり・伝染していくものなので、`Meme` 側との FK は持たない。
    """

    __tablename__ = "character"

    text: Mapped[str | None] = mapped_column(String, nullable=True, sort_order=10000)

    name: Mapped[str | None] = mapped_column(String, sort_order=210)
    kind: Mapped[str] = mapped_column(
        String, default=CHARACTER_KIND_PERSON, nullable=False,
        comment="種別。「人物」か、人物以外の対象(国・組織・商会・氏族・集団・物など)", sort_order=230)

    main_character: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="メインキャラクターか。"
        "出来事・筋書きのランダム生成は、この列が false(サブキャラクター)の人物・対象だけを対象にする",
        sort_order=240)

    start: Mapped[Stamp | None] = mapped_column(StampType, sort_order=250)
    end: Mapped[Stamp | None] = mapped_column(StampType, sort_order=260)

    # 出自(生まれの場所)は別列を持たず、CharacterPlace の一番古い行として表す。
    # 名字・体格・口調・性格は期間ごとに CharacterParameter が持ち、md では `# data` の parameters に並ぶ。
    CHILD_LISTS = ("parameters",)

    NAME_COLUMN = "name"

    def parameters_at(self, time=None) -> dict:
        return resolve_parameters(self.parameters, time)

    # relationships

    parameters: Mapped[list[CharacterParameter]] = relationship(
        back_populates="character", lazy="selectin", cascade="all, delete-orphan",
        order_by="CharacterParameter.id")
    places: Mapped[list[CharacterPlace]] = relationship(
        back_populates="character", lazy="noload", order_by="CharacterPlace.start.desc()"
    )
    events: Mapped[list[Event]] = relationship(
        secondary="event_character", viewonly=True, lazy="noload",
        order_by="Event.start.desc()"
    )


class CharacterParameter(Base):
    """人物の名字・体格・口調・性格を、期間ごとに一行で持つ。

    空の列は「この期間では決めない」。ある時刻の値は `resolve_parameters` が、その時刻に掛かる行を
    期間を限らない行から順に重ねて決める。名字・体格・口調は人物だけが持ち、人物以外の対象は空のまま。
    """

    __tablename__ = "character_parameter"

    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("character.id"), index=True, nullable=False, sort_order=100)
    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="この値が効き始める時。空なら初めから", sort_order=110)
    end: Mapped[Stamp | None] = mapped_column(
        StampType, comment="この値が効き終わる時(この時からは効かない)。空なら終わりまで", sort_order=120)

    # --- 名字 -------------------------------------------------------------
    family_name: Mapped[str | None] = mapped_column(
        String, comment="名字。結婚・養子・家の取り立てなどで変わる。名字を持たない身分なら空", sort_order=310)

    # --- 体格 -------------------------------------------------------------
    sex: Mapped[str | None] = mapped_column(String,  comment="性別", sort_order=320)
    height: Mapped[float | None] = mapped_column(DECIMAL, comment="背丈 cm", sort_order=330)
    build: Mapped[str | None] = mapped_column(String,  comment="体格", sort_order=340)

    # --- 口調 -------------------------------------------------------------
    first_person: Mapped[str | None] = mapped_column(String,  comment="一人称", sort_order=350)
    second_person: Mapped[str | None] = mapped_column(String,  comment="二人称", sort_order=360)
    third_person: Mapped[str | None] = mapped_column(String,  comment="三人称", sort_order=370)
    tone: Mapped[str | None] = mapped_column(String,  comment="口調", sort_order=380)
    dialect: Mapped[str | None] = mapped_column(
        String, comment="方言。方言の種類か、標準語で話すならその癖(語尾・言い回し・訛り)", sort_order=385)

    # --- 性格 -----------------------------------------------------------
    # 各列は PersonalityLevel の値(無/低/並/高/必)。どの行でも決めていない軸は PERSONALITY_DEFAULT。
    sincerity: Mapped[str | None] = mapped_column(String, comment="誠実性", sort_order=390)
    curiosity: Mapped[str | None] = mapped_column(String, comment="好奇心", sort_order=400)
    proactivity: Mapped[str | None] = mapped_column(String, comment="行動力", sort_order=410)
    cooperativeness: Mapped[str | None] = mapped_column(String, comment="協調性", sort_order=420)
    sociability: Mapped[str | None] = mapped_column(String, comment="社交性", sort_order=430)
    emotional_expression: Mapped[str | None] = mapped_column(String, comment="感情表現", sort_order=440)
    self_esteem: Mapped[str | None] = mapped_column(String, comment="自己肯定感", sort_order=450)
    self_efficacy: Mapped[str | None] = mapped_column(String, comment="自己効力感", sort_order=460)
    stress_resilience: Mapped[str | None] = mapped_column(String, comment="ストレス耐性", sort_order=470)
    flexibility_of_values: Mapped[str | None] = mapped_column(String, comment="価値観の柔軟性", sort_order=480)
    sensitivity: Mapped[str | None] = mapped_column(String, comment="感受性", sort_order=490)
    imagination: Mapped[str | None] = mapped_column(String, comment="想像力", sort_order=500)

    character: Mapped[Character] = relationship(back_populates="parameters", lazy="noload")

    @staticmethod
    def validate(data) -> None:
        check_personality(data)

    def covers(self, time: Stamp | None) -> bool:
        """時刻が空なら、期間を限らない行だけが掛かる。"""
        if time is None:
            return self.start is None and self.end is None
        return (self.start is None or self.start <= time) and (self.end is None or time < self.end)


def _parameter_order(row: CharacterParameter) -> tuple:
    # 期間を限る端が多い行ほど後に重ねて勝たせる。同じなら始まりの遅い行、後に足した行が勝つ
    bounds = (row.start is not None) + (row.end is not None)
    return bounds, row.start.to_int() if row.start is not None else -1, row.id or 0


def resolve_parameters(rows, time=None) -> dict:
    time = Stamp.parse(time)
    values: dict = {column: None for column in PERSON_PARAMETER_COLUMNS}
    values.update({column: PERSONALITY_DEFAULT for column in PERSONALITY_COLUMNS})
    for row in sorted((row for row in rows if row.covers(time)), key=_parameter_order):
        for column in PARAMETER_COLUMNS:
            value = getattr(row, column)
            if value is not None:
                values[column] = float(value) if isinstance(value, Decimal) else value
    return values


class CharacterPlace(Base):

    __tablename__ = "character_place"

    character_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("character.id"), sort_order=100)
    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("location.id"), sort_order=110)

    start: Mapped[Stamp | None] = mapped_column(StampType, sort_order=120)
    end: Mapped[Stamp | None] = mapped_column(StampType, sort_order=130)

    character: Mapped[Character | None] = relationship(back_populates="places", lazy="noload")
    place: Mapped[Location] = relationship(lazy="noload")


class CharacterRelation(MarkdownBase):
    """`character_id_1` から見た `character_id_2` との関係を一行で持つ。"""

    __tablename__ = "character_relation"

    character_id_1: Mapped[int] = mapped_column(
        Integer, ForeignKey("character.id"), index=True,
        comment="関係の主体となる人物", sort_order=100)
    character_id_2: Mapped[int] = mapped_column(
        Integer, ForeignKey("character.id"), index=True,
        comment="関係の相手となる人物", sort_order=110)
    relation: Mapped[str] = mapped_column(
        String, nullable=False, comment="関係の短い名前(母・師・宿敵 など)", sort_order=120)

    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="この関係が始まる時。空なら初めから", sort_order=130)
    end: Mapped[Stamp | None] = mapped_column(
        StampType, comment="この関係が終わる時。空なら続いている", sort_order=140)

    def default_filename(self) -> str | None:
        return f"{self.character_id_1}_{self.character_id_2}"

    character_1: Mapped["Character"] = relationship(
        foreign_keys="CharacterRelation.character_id_1", lazy="noload")
    character_2: Mapped["Character"] = relationship(
        foreign_keys="CharacterRelation.character_id_2", lazy="noload")


class Idea(FactCheckMixin, MemeSeededMixin, MarkdownBase):
    __tablename__ = "idea"

    name: Mapped[str] = mapped_column(String, sort_order=200)
    kind: Mapped[str] = mapped_column(String, comment="種別(技術・制度・概念など)", sort_order=210)
    auto_generated: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="本文から自動で足した未確認のアイデアか。検索・生成には他と同じく出る。確かめたら false にする",
        sort_order=215)

    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"), index=True,
        comment="効く場所。この場所とその配下で効く。空ならどこにも効かない", sort_order=220)
    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="効き始める時刻。出来事の時刻と比べる。空なら始まりを限らない", sort_order=230)
    end: Mapped[Stamp | None] = mapped_column(
        StampType, comment="効き終わる時刻(この時刻からは効かない)。空なら終わりを限らない", sort_order=240)

    parent_idea_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("idea.id"), comment="上位のアイデア。置いたディレクトリで決まる", sort_order=250)
    alias_of_idea_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("idea.id"), index=True,
        comment="作中での呼び名であるときの、本質のアイデア。呼び名は location_id・start・end の場所と時代で使い、"
                "空の列はどこでも・いつでも使う。当てはまる呼び名が無ければ本質の name をそのまま使う",
        sort_order=260)

    NAME_COLUMN = "name"


class Story(EventSeededMixin, MarkdownBase):

    __tablename__ = "story"

    name: Mapped[str] = mapped_column(String, sort_order=200)

    world_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"), comment="使用する世界線", sort_order=210)
    world: Mapped[Location | None] = relationship(
        foreign_keys="Story.world_id", lazy="noload")
    place_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"), comment="立つ場所。断面を取るのに使う", sort_order=220)
    place: Mapped[Location | None] = relationship(
        foreign_keys="Story.place_id", lazy="noload")
    narration: Mapped[str] = mapped_column(String,  comment="語り", sort_order=230)
    state: Mapped[str] = mapped_column(String,  comment="状態", sort_order=240)

    start: Mapped[Stamp | None] = mapped_column(StampType, comment="立つ年", sort_order=250)
    end: Mapped[Stamp | None] = mapped_column(StampType, sort_order=260)

    plots: Mapped[list["Plot"]] = relationship(
        back_populates="story", lazy="noload",
        order_by="[Plot.start.asc().nulls_last(), Plot.id.asc()]")

    NAME_COLUMN = "name"
    MARKDOWN_OWN_DIRECTORY = True


class Plot(EventSeededMixin, MarkdownBase):
    """話の枠(プロット)。種・時刻・視点・場所までを持ち、本文は `Episode` が持つ。"""

    __tablename__ = "plot"

    TEXT_SECTIONS = ("key",)
    MARKDOWN_PARENT = "story"
    NAME_COLUMN = "title"

    # 本文は Episode へ分けたので、MarkdownBase の text 列を持たない。
    # 古い書き方(`plot.text`)を黙って素通りさせないよう、読み書きとも止める
    @property
    def text(self):
        raise AttributeError("話の本文は Plot.body(書き込みは Episode)にある")

    @text.setter
    def text(self, _value):
        raise AttributeError("話の本文は Episode に書く")

    story_id: Mapped[int] = mapped_column(Integer, ForeignKey("story.id"), sort_order=200)
    story: Mapped[Story] = relationship(back_populates="plots", lazy="noload")
    title: Mapped[str] = mapped_column(
        String,  comment="サブタイトル。本文の見出しから読む", sort_order=220)
    synced: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="同期フラグ。この話の出来事・行動が台帳へ戻してあるか。"
                "自動生成時はオン、手で書いたときはオフ。"
                "オフの話があるあいだは、次の話の材料を読み出せない",
        sort_order=240)

    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="話が立つ時刻。作品の中の話はこの順に並ぶ(空の話は後ろに id 順)", sort_order=250)
    end: Mapped[Stamp | None] = mapped_column(StampType, sort_order=260)
    viewpoint: Mapped[str | None] = mapped_column(
        String, comment="視点。誰に寄って語るか(「ノア(十四歳)」「アウレア / ミレア」)", sort_order=270)
    place: Mapped[str | None] = mapped_column(
        String, comment="場所。自由記述(「ヴァレンツァ 外れの川」)", sort_order=280)

    key: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default="",
        comment="キーテキスト。作者が入れる、AI 生成前の種。md では `# key` の節",
        sort_order=9990)

    episode: Mapped["Episode | None"] = relationship(
        back_populates="plot", lazy="selectin", uselist=False)

    @property
    def body(self) -> str:
        """本文。まだ書いていない話(枠)は空文字"""
        return self.episode.text if self.episode is not None else ""

    def default_filename(self) -> str | None:
        return self.title or None

    @property
    def markdown_name(self) -> str:
        head = f"{self.story_id}_{plot_stamp_stem(self.start)}"
        return f"{head}_{self.title.replace('/', '／')}.md" if self.title else f"{head}.md"

    @classmethod
    def parse_markdown_stem(cls, stem: str) -> tuple[int | None, dict]:
        # 名前は id を持たない({story_id}_{start}_{title})。行の取り違えを避けるため id は `# data` から読む
        story_part, _, rest = stem.partition("_")
        if not story_part.isdigit():
            return super().parse_markdown_stem(stem)
        stamp_part, _, title_part = rest.partition("_")
        if stamp_part == "" or _PLOT_STAMP.match(stamp_part):
            return None, {"story_id": int(story_part), "start": parse_plot_stamp_stem(stamp_part),
                          "title": title_part or None}
        return None, {"story_id": int(story_part), "title": rest or None}


class Episode(MarkdownBase):
    """話の本文。プロット(`Plot`)とは分けて生成し、プロットの md の隣に同じ名前の .txt で本文だけを出す。"""

    __tablename__ = "episode"

    MARKDOWN_PARENT = "plot"
    BODY_FILE_EXTENSION = ".txt"

    plot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plot.id"), unique=True, index=True, nullable=False, sort_order=200)
    plot: Mapped[Plot] = relationship(back_populates="episode", lazy="noload")
    letters: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="字数。本文から数える", sort_order=210)
    model: Mapped[str | None] = mapped_column(
        String, comment="本文を書いたモデル。空なら不明(手で書いた本文など)", sort_order=220)
    effort: Mapped[str | None] = mapped_column(
        String, comment="本文を書いたときの effort。空なら不明(手で書いた本文など)", sort_order=230)

    @validates("text")
    def _letters_follow_text(self, _key, value):
        self.letters = len(value or "")
        return value

    @classmethod
    def parse_markdown_stem(cls, stem: str) -> tuple[int | None, dict]:
        # 名前はプロットの md と同じなので、行は置き場所(隣のプロット)から決める
        return None, {}


_PLOT_STAMP = re.compile(r"^\d+-\d{2}-\d{2}-\d{4}$")


def plot_stamp_stem(start: Stamp | None) -> str:
    """プロットの md 名の時刻。`/` `:` を名前に置けないので `年-月-日-時分` にする。空なら空文字"""
    if start is None:
        return ""
    return f"{start.year}-{start.month:02d}-{start.day:02d}-{start.hour:02d}{start.minute:02d}"


def parse_plot_stamp_stem(stem: str) -> Stamp | None:
    if not stem:
        return None
    year, month, day, clock = stem.split("-")
    return Stamp(int(year), int(month), int(day), int(clock[:2]), int(clock[2:]))


class EpisodeSummary(Base):
    """話の本文(`Episode`)の概要と文体の覚え書き。md には出さない。"""

    __tablename__ = "episode_summary"

    story_id: Mapped[int] = mapped_column(Integer, ForeignKey("story.id"), index=True, sort_order=100)
    episode_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("episode.id"), unique=True, index=True, sort_order=110)
    source_hash: Mapped[str] = mapped_column(
        String, comment="要約した本文の sha256。本文と食い違ったら作り直す", sort_order=120)
    summary: Mapped[str] = mapped_column(String, comment="概要", sort_order=130)
    style: Mapped[str] = mapped_column(String, comment="文体の覚え書き", sort_order=140)


class EventIdea(Base):
    """出来事の本文が踏まえたアイデア。md には出さない。"""

    __tablename__ = "event_idea"
    __table_args__ = (UniqueConstraint("event_id", "idea_id"),)

    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("event.id"), index=True, sort_order=100)
    idea_id: Mapped[int] = mapped_column(Integer, ForeignKey("idea.id"), index=True, sort_order=110)


class PlotIdea(Base):
    """プロットの種から引いて本文が踏まえたアイデア。md には出さない。"""

    __tablename__ = "plot_idea"
    __table_args__ = (UniqueConstraint("plot_id", "idea_id"),)

    plot_id: Mapped[int] = mapped_column(Integer, ForeignKey("plot.id"), index=True, sort_order=100)
    idea_id: Mapped[int] = mapped_column(Integer, ForeignKey("idea.id"), index=True, sort_order=110)


class CharacterIdea(Base):
    """人物・対象の説明が踏まえたアイデア。md には出さない。"""

    __tablename__ = "character_idea"
    __table_args__ = (UniqueConstraint("character_id", "idea_id"),)

    character_id: Mapped[int] = mapped_column(Integer, ForeignKey("character.id"), index=True, sort_order=100)
    idea_id: Mapped[int] = mapped_column(Integer, ForeignKey("idea.id"), index=True, sort_order=110)


IDEA_LINK_MODELS = {Event: EventIdea, Plot: PlotIdea, Character: CharacterIdea}


# 既定値は持たない。場所を取り違えると sqlite が空の db を黙って作るので、未設定なら import で止める。
WORLD_DIR = os.environ["DEM_WORLD_DIR"]
NOVEL_DB_PATH = os.environ.get("DEM_NOVEL_DB_PATH", os.path.join(WORLD_DIR, "novel.db"))
WORLDS_ROOT = os.environ.get("DEM_WORLDS_DIR", os.path.join(WORLD_DIR, "worlds"))
DB_PATH = os.environ.get("DEM_DB_PATH", NOVEL_DB_PATH)


def create_db(path=DB_PATH):
    """台帳から何度でも組み直せるので、既にあれば消して作り直す。"""
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        # sqlite の既定も UTF-8 だが、文字化け事故を防ぐため明記しておく。
        # テーブルが空のうちしか効かないので create_all の前に打つ。
        conn.execute(text("PRAGMA encoding='UTF-8'"))
    Base.metadata.create_all(engine)
    return engine


TEST_DB_PATH = os.path.join(WORLD_DIR, "novel.test.db")


def _make_engine(path):
    return create_engine(f"sqlite:///{os.path.abspath(path)}")


engine = _make_engine(DB_PATH)
_fixed_engines = {}


def _fixed_engine(path):
    if path not in _fixed_engines:
        _fixed_engines[path] = _make_engine(path)
    return _fixed_engines[path]


def get_env_session():
    return Session(engine)


def get_novel_session():
    return Session(_fixed_engine(NOVEL_DB_PATH))


def get_test_session():
    return Session(_fixed_engine(TEST_DB_PATH))

