#!/usr/bin/env python3
from __future__ import annotations

import enum
import hashlib
import os
from datetime import datetime
from urllib.parse import quote

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, FetchedValue, Integer, String, DECIMAL, JSON, TypeDecorator,
    event,
    create_engine,
    ForeignKey,
    UniqueConstraint,
    select,
    Select,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import make_url

from db.polygon import parse_polygon
from db.postgres.timestamps import install_updated_at
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

    def load_dialect_impl(self, dialect):
        # PostgreSQL の json は等値の演算子を持たず、行ごとの DISTINCT・GROUP BY で落ちるので jsonb にする
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB(none_as_null=True))
        return dialect.type_descriptor(JSON(none_as_null=True))

    def process_bind_param(self, value, dialect):
        return parse_polygon(value)


class Base(DeclarativeBase):

    # SQLite は「INTEGER PRIMARY KEY」だけを rowid の別名として autoincrement する。
    # Integer だと型名が INTEGER と一致せず insert のたびに id が NULL のまま失敗する。
    # sort_order は列の並び順を明示するための番号。継承の段が一段深くなるごとに
    # 開始値を 100 増やし、同じクラス内では 10 刻みで振る(あとで列を挟みやすい)。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, sort_order=0)
    # 二つとも db が入れる(`db/postgres/timestamps.py`)ので、コードから書かない
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="行を作った時刻", sort_order=90000)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), server_onupdate=FetchedValue(),
        comment="行を最後に直した時刻", sort_order=90010)


# 画面・入口の欄に出さない、db が入れる列
TIMESTAMP_COLUMNS = frozenset({"created_at", "updated_at"})


@event.listens_for(Base.metadata, "after_create")
def _install_updated_at(_metadata, connection, tables, **_kw) -> None:
    if connection.dialect.name == "postgresql":
        install_updated_at(connection, [table.name for table in tables])


class ContentBase(Base):
    """作品・人物・出来事・アイデア・話など、物語の中身を文章で持つテーブルの基底。"""

    __abstract__ = True

    # 長い文章の列(GUI では大きな入力欄。TODO の検索もこの列を見る)
    TEXT_COLUMNS: tuple[str, ...] = ("text",)
    # 子の行の配列として出し入れする relationship の名前(`db/child_lists.py`)
    CHILD_LISTS: tuple[str, ...] = ()


class TextBase(ContentBase):
    """本文を `text` に持つ行。"""

    __abstract__ = True

    text: Mapped[str] = mapped_column(String,  nullable=False, sort_order=10000)


class Location(TextBase):

    __tablename__ = "location"

    name: Mapped[str | None] = mapped_column(String, sort_order=200)
    kind: Mapped[str | None] = mapped_column(String, sort_order=210)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"),
        comment="一つ上の場所。断面・知る相手・アイデアの効く場所は、この木をたどって配下の場所まで含む", sort_order=220)

    # 位置は**一つの座標系だけ**で持つ。経度・緯度・高度で持ち、
    # **どこを原点とするかは星ごとに決めて、その星の text に書く**。
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

    active_random_generation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="ランダム生成の対象にするか。出来事の生成で新設された子の場所は親の値を継ぐ。"
        "場所を名指しする出来事の生成(GenerateEvent)はこの値を見ない")

    # 自分の親(一つ上の場所)。木をのぼって道筋(location_path)を組むのに使う。
    # 書き込みは常に parent_id を直に触るので、どちらも読み取り専用にしておく
    # (viewonly を外すと、同じ外部キーを double-write しようとして SQLAlchemy が警告する)。
    parent: Mapped["Location | None"] = relationship(
        remote_side="Location.id", viewonly=True, lazy="noload")
    children: Mapped[list[Location]] = relationship(viewonly=True)

    CHILD_LISTS = ("histories",)

    histories: Mapped[list["LocationHistory"]] = relationship(
        back_populates="location", lazy="selectin", cascade="all, delete-orphan",
        order_by="LocationHistory.start.desc().nulls_last()",
        doc="場所で起きたこと・変わったことを、出来事ごとに一行で持つ。話・出来事には、その時刻までに始まった行だけを渡す。"
        "時刻が空の行は構想で、作者だけが読む")


class LocationHistory(Base):
    """場所の来歴を、起きた出来事ごとの一行で持つ子テーブル。場所の芯(時期を限らない姿)は `Location.text` に持つ。

    関係の来歴(CharacterRelationHistory)と同じく、ある時刻の話・出来事には、その時刻までに始まった行だけを渡す
    (`data_access_logic/location/reading.py` の `location_at`)ので、先の時刻の行を書き足しても、それより前には効かない。
    `start` が空の行は、起きる時期がまだ決まっていない構想で、作者が読むときだけ出す。
    行は、知る相手(`knowers`)に当たる人物だけが知る(人物の来歴・アイデアの履歴と同じ形)。既定の知る相手はその場所自身で、
    その時刻にその場所(配下も含む)に住む人物が知る。秘密は人物だけを知る相手にする。
    """

    __tablename__ = "location_history"

    location_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("location.id"), index=True, nullable=False, sort_order=100)
    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="起きた時刻(この来歴が効き始める時刻)。空なら時期が決まっていない(話・出来事には渡さない)",
        sort_order=110)
    description: Mapped[str] = mapped_column(String, nullable=False, comment="来歴", sort_order=120)

    location: Mapped[Location] = relationship(back_populates="histories", lazy="noload")
    # 人物役(`data_access_logic/character/knowledge.py`)には、知る相手に当たる人物にだけ渡す
    knowers: Mapped[list["LocationHistoryKnower"]] = relationship(
        back_populates="history", lazy="selectin", cascade="all, delete-orphan", order_by="LocationHistoryKnower.id")

    def covers(self, time: Stamp) -> bool:
        return self.start is not None and self.start <= time


class Event(TextBase):

    __tablename__ = "event"

    name: Mapped[str] = mapped_column(String, sort_order=200)
    hidden: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="場所の断面(ReadBrief)に出さないか。true なら full で読むときだけ出す。分類は持たず、name・text の書き方で表す",
        sort_order=210)
    time: Mapped[Stamp] = mapped_column(StampType, index=True, sort_order=220)

    parent_event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("event.id"), comment="上位の出来事(この出来事を含む大きな出来事)", sort_order=230)

    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"), index=True,
        comment="起きた場所。場所の断面(ReadBrief)は、その場所と配下で起きた出来事を読む", sort_order=240)
    location: Mapped[Location | None] = relationship(lazy="noload")

    # 行動もここに入る(人物の行動に別表は無い)。誰の行動かは
    # event_character(中間テーブル、多対多)が持つ。空なら
    # 誰の行動でもない「ただ起きたこと」。
    event_characters: Mapped[list["EventCharacter"]] = relationship(
        back_populates="event", lazy="noload", cascade="all, delete-orphan", order_by="EventCharacter.id")

    start: Mapped[Stamp | None] = mapped_column(StampType, sort_order=250)
    end: Mapped[Stamp | None] = mapped_column(StampType, sort_order=260)

    parent_event: Mapped["Event | None"] = relationship(
        remote_side="Event.id", back_populates="child_events", lazy="noload"
    )
    child_events: Mapped[list["Event"]] = relationship(
        back_populates="parent_event", lazy="noload", cascade="all, delete-orphan"
    )
    summary: Mapped["EventSummary | None"] = relationship(lazy="noload", viewonly=True)


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


class Meme(TextBase):
    """ミームは移り変わり・伝染していくものなので、どの元から抜き出したか、どの人物が持つかは持たない。
    ミームどうしで持つのは、反転した対(アンチミーム)だけ。
    """

    __tablename__ = "meme"

    category: Mapped[str | None] = mapped_column(
        String, nullable=True,
        comment=f"分類。{'/'.join(MEME_CATEGORIES)} のいずれか。空なら次の抽出で AI が振る",
        sort_order=200)
    anti_meme_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("meme.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="反転したミーム(アンチミーム)。対の二行が互いを指す。空なら次の抽出で AI が作る",
        sort_order=210)


class Oracle(TextBase):
    """著者自身の創作・AI についての覚え書き。物語のデータではない。"""

    __tablename__ = "oracle"

    title: Mapped[str | None] = mapped_column(String, comment="題。覚え書きを呼ぶ名前", sort_order=200)


class StyleScope(enum.StrEnum):
    # 全体は AI が書くすべての文に効く。残りは使う所ごとの範囲で、使う所は
    # 全体 → 作品の指示(story.instruction) → その範囲 → 話の指示(episode.instruction) の順に足す
    ALL = "全体"
    EPISODE = "本文"
    PLOT = "プロット"
    CHARACTER = "人物"
    HISTORY = "来歴"
    EVENT = "出来事"
    IDEA = "アイデア"
    MEME = "ミーム"
    RELATION = "関係"
    # 仕事ごとの指示(AI の system に渡す)。「<上の範囲>:<仕事>」の形で、上の範囲の書き方と一緒に渡す。
    # 仕事に共通する文は上の範囲の行に書く
    FACT_CHECK = "全体:検証"
    PLOT_FRAME = "プロット:枠"
    PLOT_REWRITE = "プロット:書き直し"
    PLOT_CASTING = "プロット:人物と舞台"
    CHARACTER_CONTENT = "人物:生成"
    THING_CONTENT = "人物:対象の生成"
    CHARACTER_ELEMENTS = "人物:筋書きの要素"
    CHARACTER_CONSISTENCY = "人物:整合"
    NAME_MEANING = "人物:名の意味"
    CHARACTER_NAMING = "人物:名づけ"
    THING_NAMING = "人物:対象の名づけ"
    CHARACTER_VOICES = "人物:話し方"
    CHARACTER_MOVES = "人物:居場所の移動"
    EVENT_CANDIDATES = "出来事:候補"
    EVENT_RECORD = "出来事:記録"
    EVENT_TEXT = "出来事:本文の後埋め"
    EVENT_SUMMARY = "出来事:要約"
    EVENT_SEEDS = "出来事:種の抜き出し"
    EVENT_SEED_MERGE = "出来事:種のまとめ"
    IDEA_TERMS = "アイデア:語の抜き出し"
    MEME_EXTRACT = "ミーム:抜き出し"
    MEME_DEDUPE = "ミーム:重複"
    MEME_ANTI = "ミーム:アンチ"
    MEME_CLASSIFY = "ミーム:分類"
    EPISODE_RELATIONS = "関係:話の関係"

    @property
    def wide(self) -> "StyleScope":
        """仕事ごとの指示なら、その上の範囲。上の範囲そのものなら自分。"""
        head, _, task = self.value.partition(":")
        return StyleScope(head) if task else self


STYLE_SCOPES = tuple(scope.value for scope in StyleScope)


class StylePreference(TextBase):
    """AI に書かせる文の指示(文体・作風・注意書き)。範囲ごとに一行。
    使う所は、全体の行 → 作品の指示 → その範囲の行 → 話の指示 の順に、書くたびに db から読んで足す。
    初期値はコードに持たない。行の無い範囲は何も足さない。"""

    __tablename__ = "style_preference"

    scope: Mapped[str] = mapped_column(
        String, nullable=False, unique=True,
        comment="効く範囲(`StyleScope`)。範囲ごとに一行。全体は AI が書くすべての文に、使う所の範囲(本文・プロットなど)は"
                "その所だけに効く。「<範囲>:<仕事>」は仕事ごとの指示で、上の範囲の行と重ねて渡す",
        sort_order=200)


CHARACTER_KIND_PERSON = "人物"


class PersonalityLevel(enum.StrEnum):
    NONE = "無"
    LOW = "低"
    NORMAL = "並"
    HIGH = "高"
    MUST = "必"


PERSONALITY_LEVELS = tuple(level.value for level in PersonalityLevel)

# マスターテーブル `personality_level` の行の id(1始まり、上の宣言順)。
# マイグレーションはこの順で行を挿入するので、ここでの並びを変えたら移行も合わせて直す。
_PERSONALITY_LEVEL_IDS = {level.value: index + 1 for index, level in enumerate(PersonalityLevel)}
_PERSONALITY_LEVEL_LABELS = {id_: label for label, id_ in _PERSONALITY_LEVEL_IDS.items()}


class PersonalityLevelType(TypeDecorator):
    """性格12列。db には `personality_level`(無/低/並/高/必の5行だけのマスター)の id で持ち、
    Python 側は文字列(無/低/並/高/必)のまま扱えるようにする。
    """

    impl = Integer
    cache_ok = True

    @property
    def python_type(self) -> type:
        return str

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if value in _PERSONALITY_LEVEL_IDS:
            return _PERSONALITY_LEVEL_IDS[value]
        raise ValueError(f"性格は {'/'.join(PERSONALITY_LEVELS)} のいずれか: {value!r}")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _PERSONALITY_LEVEL_LABELS.get(value, value)


class PersonalityLevelOption(Base):
    """`personality_level` マスター。性格12列(誠実性など)から FK で引かれる、無/低/並/高/必の5行だけ。"""

    __tablename__ = "personality_level"

    name: Mapped[str] = mapped_column(String, nullable=False, sort_order=10)


PERSONALITY_COLUMNS = (
    "sincerity", "curiosity", "proactivity", "cooperativeness", "sociability",
    "emotional_expression", "self_esteem", "self_efficacy", "stress_resilience",
    "flexibility_of_values", "sensitivity", "imagination",
)


PERSON_PARAMETER_COLUMNS = (
    "family_name", "sex", "height", "build", "first_person", "second_person", "third_person", "tone", "dialect",
)


class KnowerMixin:
    """来歴・履歴を知る相手と、知った時刻(`data_access_logic/character/knowledge.py`)。

    知る相手は人物か場所のどちらか一方。場所なら、その時刻にその場所(配下も含む)に住む人物が知る。誰もが知ることは世界の場所で表す。
    """

    knower_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("character.id"), index=True, comment="知る人物", sort_order=110)
    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"), index=True,
        comment="知る場所。その時刻にこの場所(配下も含む)に住む人物が知る", sort_order=120)
    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="知った時刻。空ならいつ知ったか決まっておらず、人物役には渡さない", sort_order=130)


def _knower_args(table: str, subject: str) -> tuple:
    return (UniqueConstraint(subject, "knower_id"), UniqueConstraint(subject, "location_id"),
            CheckConstraint("(knower_id IS NULL) <> (location_id IS NULL)", name=f"ck_{table}_one_knower"))


class Character(ContentBase):
    """人物に限らず、国・組織・集団・物も一行として持つ(`kind` で区別)。

    ミームは人物どうしで移り変わり・伝染していくものなので、`Meme` 側との FK は持たない。
    人物の芯(説明・meme・行動原理・plot)は `text` に、出来事ごとの来歴は `CharacterHistory` に持つ。
    """

    __tablename__ = "character"

    # 長い文章の列。人物役(`data_access_logic/character/knowledge.py`)には、外見は会った相手に、芯は知る相手に、
    # meme と行動原理は本人だけに渡り、plot はだれにも渡らない(作者だけが読む)
    # 一覧の頭・呼び名には先頭の空でない列を使うので、芯を先に置く
    TEXT_COLUMNS = ("text", "appearance", "meme", "principle", "plot")

    appearance: Mapped[str | None] = mapped_column(
        String, comment="外見。見て分かること(顔立ち・体つき・身なり・目に見える持ち物)", sort_order=9990)
    text: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="人物の芯(経歴・立場・性格の説明)。いつの話・出来事にも渡す。本人と関係のある人物が知る", sort_order=10000)
    meme: Mapped[str | None] = mapped_column(
        String, comment="持つミーム。`- <古今表裏>: <文面>` の箇条書き", sort_order=10010)
    principle: Mapped[str | None] = mapped_column(
        String, comment="行動原理(ミームどうしの関係と、その人物を動かすもの)", sort_order=10020)
    plot: Mapped[str | None] = mapped_column(
        String, comment="その人物について作者が進めたい筋書き", sort_order=10030)

    name: Mapped[str | None] = mapped_column(String, sort_order=210)
    kind: Mapped[str] = mapped_column(
        String, default=CHARACTER_KIND_PERSON, nullable=False,
        comment="種別。「人物」か、人物以外の対象(国・組織・商会・氏族・集団・物など)", sort_order=230)

    main_character: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="メインキャラクターか。"
        "出来事・筋書きのランダム生成は、この列が false(サブキャラクター)の人物・対象だけを対象にする",
        sort_order=240)
    end: Mapped[Stamp | None] = mapped_column(
        StampType, comment="没年(この時からはいない)。空なら死んでいない", sort_order=250)

    # 出自(生まれの場所)は別列を持たず、CharacterLocation の一番古い行として表す。
    # 名字・体格・口調・性格は CharacterParameter が、居場所は期間ごとに CharacterLocation が持ち、
    # 入口では `parameters` / `locations` の配列で出し入れする。誕生も専用の列を持たず、
    # `parameters` の一番早く始まる行の start として表す(下の `start`)。
    # 出来事ごとの来歴は CharacterHistory が持ち、入口では `histories` の配列で出し入れする
    # (Idea の `histories` と同じく、基本の本文に時代ごとの行を足す形)。
    CHILD_LISTS = ("parameters", "locations", "histories")

    @property
    def start(self) -> Stamp | None:
        """誕生。`parameters` の一番早く始まる行の start(どの行も空なら不明)。"""
        starts = [row.start for row in self.parameters if row.start is not None]
        return min(starts) if starts else None

    @start.setter
    def start(self, value) -> None:
        row = self.parameters[0] if self.parameters else CharacterParameter()
        if not self.parameters:
            self.parameters.append(row)
        row.start = Stamp.parse(value)

    # relationships

    parameters: Mapped[list[CharacterParameter]] = relationship(
        back_populates="character", lazy="selectin", cascade="all, delete-orphan",
        order_by="CharacterParameter.id",
        doc="名字・体格・口調・性格を、変わった時ごとに一行で持つ。行は start から先ずっと効き、後に始まる行が上書きする。"
        "一番早く始まる行の start が誕生")
    locations: Mapped[list[CharacterLocation]] = relationship(
        back_populates="character", lazy="selectin", cascade="all, delete-orphan",
        order_by="CharacterLocation.start.desc().nulls_last()",
        doc="住まい・拠点を期間ごとに一行で持つ。一番古い行が出自。出来事の当事者はこの居場所から選び、"
        "場所を知る相手にした来歴は、その時刻にそこ(配下も含む)に住む人物が知る"
    )
    histories: Mapped[list["CharacterHistory"]] = relationship(
        back_populates="character", lazy="selectin", cascade="all, delete-orphan",
        order_by="CharacterHistory.start.desc().nulls_last()",
        doc="来歴を、起きた出来事ごとに一行で持つ。装い・持ち物・記憶・隠し事は種別を付けた行にする。"
        "話・出来事には、その時刻までに始まり、まだ終わっていない行だけを渡す。時刻が空の行は構想で、作者だけが読む。行は知る相手だけが知る"
    )
    events: Mapped[list[Event]] = relationship(
        secondary="event_character", viewonly=True, lazy="noload",
        order_by="Event.start.desc().nulls_last()"
    )


class CharacterParameter(Base):
    """人物の名字・体格・口調・性格を、変わった時ごとに一行で持つ。

    行は `start` から先ずっと効き、終わりを持たない(後に始まる行が上書きする)。空の列は「この行では決めない」。
    ある時刻の値は `data_access_logic/character/parameters.py` の `parameters_at` が、その時刻までに始まった行を
    始まりの古い順に重ねて決める。名字・体格・口調は人物だけが持ち、人物以外の対象は空のまま。
    装い・持ち物は値の変わるたびに行が増えるので、ここでは持たず、来歴(CharacterHistory)に種別を付けた行で持つ。
    """

    __tablename__ = "character_parameter"

    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("character.id"), index=True, nullable=False, sort_order=100)
    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="この値が効き始める時。空なら初めから", sort_order=110)

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
    # 各列は personality_level への FK(Python 側は PersonalityLevel の値、無/低/並/高/必のまま扱える)。
    # どの行でも決めていない軸は「並」(`data_access_logic/character/parameters.py`)。
    sincerity: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="誠実性", sort_order=390)
    curiosity: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="好奇心", sort_order=400)
    proactivity: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="行動力", sort_order=410)
    cooperativeness: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="協調性", sort_order=420)
    sociability: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="社交性", sort_order=430)
    emotional_expression: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="感情表現", sort_order=440)
    self_esteem: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="自己肯定感", sort_order=450)
    self_efficacy: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="自己効力感", sort_order=460)
    stress_resilience: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="ストレス耐性", sort_order=470)
    flexibility_of_values: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="価値観の柔軟性", sort_order=480)
    sensitivity: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="感受性", sort_order=490)
    imagination: Mapped[str | None] = mapped_column(
        PersonalityLevelType, ForeignKey("personality_level.id"), comment="想像力", sort_order=500)

    character: Mapped[Character] = relationship(back_populates="parameters", lazy="noload")

    def covers(self, time: Stamp) -> bool:
        return self.start is None or self.start <= time


class CharacterLocation(Base):

    __tablename__ = "character_location"

    character_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("character.id"), sort_order=100)
    location_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("location.id"), comment="住まい・拠点にする場所", sort_order=110)

    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="住み始めた時刻。空なら初めから", sort_order=120)
    end: Mapped[Stamp | None] = mapped_column(
        StampType, comment="離れた時刻(この時刻からはいない)。空ならまだいる", sort_order=130)

    character: Mapped[Character | None] = relationship(back_populates="locations", lazy="noload")
    location: Mapped[Location] = relationship(lazy="noload")


class CharacterRelation(TextBase):
    """`character_1_id` から見た `character_2_id` との関係を一行で持つ。

    `text` は時期を限らない関係の芯(どういう間柄か)。関係の中で起きたこと・変わったことは、人物の来歴と同じく
    起きた出来事ごとの行(CharacterRelationHistory)に積み、入口では `histories` の配列で出し入れする。
    """

    __tablename__ = "character_relation"

    character_1_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("character.id"), index=True,
        comment="関係の主体となる人物", sort_order=100)
    character_2_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("character.id"), index=True,
        comment="関係の相手となる人物", sort_order=110)
    relation: Mapped[str] = mapped_column(
        String, nullable=False, comment="関係の短い名前(母・師・宿敵 など)", sort_order=120)

    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="この関係が始まる時。空なら初めから", sort_order=130)
    end: Mapped[Stamp | None] = mapped_column(
        StampType, comment="この関係が終わる時。空なら続いている", sort_order=140)

    character_1: Mapped["Character"] = relationship(
        foreign_keys="CharacterRelation.character_1_id", lazy="noload")
    character_2: Mapped["Character"] = relationship(
        foreign_keys="CharacterRelation.character_2_id", lazy="noload")

    CHILD_LISTS = ("histories",)

    histories: Mapped[list["CharacterRelationHistory"]] = relationship(
        back_populates="relation_row", lazy="selectin", cascade="all, delete-orphan",
        order_by="CharacterRelationHistory.start.desc().nulls_last()",
        doc="関係の中で起きたこと・変わったことを、出来事ごとに一行で持つ。話・人物役には、その時刻までに始まった行だけを渡す。"
        "時刻が空の行は構想で、作者だけが読む")


class CharacterRelationHistory(Base):
    """関係の来歴を、起きた出来事ごとの一行で持つ子テーブル。関係の芯は `CharacterRelation.text` に持つ。

    人物の来歴(CharacterHistory)と同じく、ある時刻の話・人物役には、その時刻までに始まった行だけを渡す
    (`data_access_logic/character/cast.py` の `relations_at`)ので、先の時刻の行を書き足しても、それより前には効かない。
    `start` が空の行は、起きる時期がまだ決まっていない構想で、作者が読むときだけ出す。
    """

    __tablename__ = "character_relation_history"

    character_relation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("character_relation.id"), index=True, nullable=False, sort_order=100)
    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="起きた時刻(この来歴が効き始める時刻)。空なら時期が決まっていない(話・人物役には渡さない)",
        sort_order=110)
    description: Mapped[str] = mapped_column(String, nullable=False, comment="来歴", sort_order=120)

    # `relation` は関係の名前の列と重なるので、親の行は `relation_row` と呼ぶ
    relation_row: Mapped[CharacterRelation] = relationship(back_populates="histories", lazy="noload")

    def covers(self, time: Stamp) -> bool:
        return self.start is not None and self.start <= time


class CharacterHistory(Base):
    """人物の来歴を、起きた出来事ごとの一行で持つ子テーブル。人物の芯は `Character.text` に持つ。

    時が進むにつれて起きたこと・変わった立場・境遇などを、起きた時刻を `start` にした行として書き足す。
    装い・持ち物・記憶・隠し事のように出来事でないものも、種別(`kind`)を付けた行で持つ。装いは身に着けた物ごとに一行にし、
    外した・失った時刻を `end` にする(その時刻に効いている装いの行をすべて重ねたものが見た目になる)。
    一つの行に時期の違う出来事をまとめない(同じ年でも、後の出来事が前の時刻の話に漏れ、知る相手も分けられなくなる)。
    ある時刻の話・出来事には、その時刻までに始まり、まだ終わっていない行だけを渡す(`data_access_logic/character/histories.py`)ので、
    先の時刻の行を書き足しても、それより前の話・出来事には効かない。
    `start` が空の行は、起きる時期がまだ決まっていない構想で、作者が読むときだけ出し、話・出来事には渡さない。
    行は、知る相手(`knowers`)に当たる人物だけが知る(本人も、知る相手に入っていなければ知らない。アイデアの履歴と同じ形)。
    """

    __tablename__ = "character_history"

    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("character.id"), index=True, nullable=False, sort_order=100)
    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="起きた時刻(この来歴が効き始める時刻)。空なら時期が決まっていない(話・出来事には渡さない)",
        sort_order=110)
    end: Mapped[Stamp | None] = mapped_column(
        StampType, comment="効き終わる時刻(この時刻からは効かない)。空なら終わりを限らない", sort_order=115)
    kind: Mapped[str | None] = mapped_column(
        String, comment="種別(装い・持ち物・記憶・隠し事など)。空なら起きた出来事", sort_order=120)
    description: Mapped[str] = mapped_column(String, nullable=False, comment="来歴", sort_order=130)

    character: Mapped[Character] = relationship(back_populates="histories", lazy="noload")
    # 人物役(`data_access_logic/character/knowledge.py`)には、知る相手に当たる人物にだけ渡す
    knowers: Mapped[list["CharacterHistoryKnower"]] = relationship(
        back_populates="history", lazy="selectin", cascade="all, delete-orphan", order_by="CharacterHistoryKnower.id")

    def covers(self, time: Stamp) -> bool:
        return self.start is not None and self.start <= time and (self.end is None or time < self.end)



class CharacterHistoryKnower(KnowerMixin, Base):
    """人物の来歴の行を知る相手。この行に当たる人物だけが来歴を知る。"""

    __tablename__ = "character_history_knower"
    __table_args__ = _knower_args("character_history_knower", "character_history_id")

    character_history_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("character_history.id"), index=True, nullable=False, sort_order=100)

    history: Mapped[CharacterHistory] = relationship(back_populates="knowers", lazy="noload")
    knower: Mapped["Character | None"] = relationship(lazy="noload")


class CharacterSkill(TextBase):
    """人物の持つスキル(技・術・技能)を一行で持つ。

    本文(`text`)はスキルの本質(何ができるか・仕組み・限界)で、アイデアの本文と同じく作者(語り部と、話を書くセッションの Claude)
    だけが読み、人物役にも AI の生成にも渡さない。身につけた・伸びた・衰えたなど、作中で起きたことは、人物の来歴と同じく
    起きた出来事ごとの行(CharacterSkillHistory)に積み、入口では `histories` の配列で出し入れする。人物が知るのはその行だけ。
    """

    __tablename__ = "character_skill"

    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("character.id"), index=True, nullable=False, comment="スキルを持つ人物", sort_order=100)
    name: Mapped[str] = mapped_column(String, nullable=False, comment="スキルの名前", sort_order=200)
    text: Mapped[str] = mapped_column(
        String, nullable=False, comment="スキルの本質(何ができるか・仕組み・限界)。作者だけが読み、人物役には渡さない",
        sort_order=10000)

    character: Mapped[Character] = relationship(lazy="noload")

    CHILD_LISTS = ("histories",)

    histories: Mapped[list["CharacterSkillHistory"]] = relationship(
        back_populates="skill", lazy="selectin", cascade="all, delete-orphan",
        order_by="CharacterSkillHistory.start.desc().nulls_last()",
        doc="身につけた・伸びた・衰えたなどを、出来事ごとに一行で持つ。話・人物役には、その時刻までに始まった行だけを渡し、"
        "その時刻までに始まった行の無いスキルは、まだ持っていないものとして渡さない。時刻が空の行は構想で、作者だけが読む。"
        "行は知る相手だけが知る")


class CharacterSkillHistory(Base):
    """スキルの来歴を、起きた出来事ごとの一行で持つ子テーブル。スキルの本質は `CharacterSkill.text` に持つ。

    人物の来歴(CharacterHistory)と同じく、ある時刻の話・人物役には、その時刻までに始まった行だけを渡すので、
    先の時刻の行を書き足しても、それより前には効かない。`start` が空の行は、起きる時期がまだ決まっていない構想で、作者が読むときだけ出す。
    行は、知る相手(`knowers`)に当たる人物だけが知る(本人も、知る相手に入っていなければ知らない)。
    """

    __tablename__ = "character_skill_history"

    character_skill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("character_skill.id"), index=True, nullable=False, sort_order=100)
    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="起きた時刻(この来歴が効き始める時刻)。空なら時期が決まっていない(話・人物役には渡さない)",
        sort_order=110)
    description: Mapped[str] = mapped_column(
        String, nullable=False, comment="来歴(身につけた・伸びた・衰えたなど、作中で起きたこと)", sort_order=120)

    skill: Mapped[CharacterSkill] = relationship(back_populates="histories", lazy="noload")
    # 人物役(`data_access_logic/character/knowledge.py`)には、知る相手に当たる人物にだけ渡す
    knowers: Mapped[list["CharacterSkillHistoryKnower"]] = relationship(
        back_populates="history", lazy="selectin", cascade="all, delete-orphan",
        order_by="CharacterSkillHistoryKnower.id")

    def covers(self, time: Stamp) -> bool:
        return self.start is not None and self.start <= time


class CharacterSkillHistoryKnower(KnowerMixin, Base):
    """スキルの来歴の行を知る相手。この行に当たる人物だけが来歴を知る。"""

    __tablename__ = "character_skill_history_knower"
    __table_args__ = _knower_args("character_skill_history_knower", "character_skill_history_id")

    character_skill_history_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("character_skill_history.id"), index=True, nullable=False, sort_order=100)

    history: Mapped[CharacterSkillHistory] = relationship(back_populates="knowers", lazy="noload")
    knower: Mapped["Character | None"] = relationship(lazy="noload")


class Idea(TextBase):
    __tablename__ = "idea"

    name: Mapped[str] = mapped_column(String, sort_order=200)
    kind: Mapped[str] = mapped_column(String, comment="種別(技術・制度・概念など)", sort_order=210)

    # 効く場所・時期は本体に持たず、履歴の行の場所・期間で持つ(`dictionary_query.idea_in_scope`)
    parent_idea_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("idea.id"), comment="上位のアイデア", sort_order=250)

    # 本文(`text`)は本質で、作者(語り部と、話を書くセッションの Claude)だけが読み、AI の生成には渡さない。作中の人物が知ることは、場所・時代ごとの作中での呼び名と
    # 受け止め方として、人物の来歴と同じく履歴(IdeaHistory)に積む。GUI では histories に並ぶ。
    CHILD_LISTS = ("histories",)

    histories: Mapped[list["IdeaHistory"]] = relationship(
        back_populates="idea", lazy="selectin", cascade="all, delete-orphan",
        order_by="IdeaHistory.start.desc().nulls_last()",
        doc="作中での呼び名と受け止め方を、場所・時代ごとに一行で持つ。作中の人物が知ることのできるのはこの行だけ(本文は作者だけが読む)。"
        "行は知る相手だけが知る")


class IdeaHistory(Base):
    """アイデアの履歴。作中での呼び名と受け止め方(作中の人物が知っていること)を、場所・時代ごとに一行で持つ。

    語り部と話を書くセッションの Claude には、話の時刻までに始まったアイデアをすべて渡し、作中の呼び名は話の時刻・場所に効く行から選ぶ。

    `location_id` の場所とその配下、`start` から `end` の手前までのあいだ効き、空の列はどこでも・いつでも効く。
    当てはまる行が無ければ本質の `name` をそのまま使う(`data_access_logic/idea/alias.py` の `called`)。
    行は、場所・期間に関わらず知る相手(`knowers`)に当たる人物だけが知る。場所・期間は、アイデアの効く範囲と作中の呼び名を決めるのにだけ使う。
    効く場所・時代にいる人物は、この名前でアイデアを認識している前提で本文を書く(`ai/instructions/idea_context.py`)。
    """

    __tablename__ = "idea_history"

    idea_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("idea.id"), index=True, nullable=False, sort_order=100)
    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"),
        comment="効く場所。この場所とその配下で効く。空ならどこでも効く", sort_order=110)
    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="効き始める時刻。空なら始まりを限らない", sort_order=120)
    end: Mapped[Stamp | None] = mapped_column(
        StampType, comment="効き終わる時刻(この時刻からは効かない)。空なら終わりを限らない", sort_order=130)
    name: Mapped[str] = mapped_column(String, nullable=False, comment="この場所・時代での作中の呼び名", sort_order=140)
    detail: Mapped[str | None] = mapped_column(
        String, comment="作中での受け止め方(作中の人物が、このアイデアについて知っていること)", sort_order=150)

    idea: Mapped[Idea] = relationship(back_populates="histories", lazy="noload")
    # 人物役(`data_access_logic/character/knowledge.py`)には、知る相手に当たる人物にだけ渡す。
    # アイデアの本文は人物役に渡さないので、人物が知ることのできるアイデアはこの行だけ
    knowers: Mapped[list["IdeaHistoryKnower"]] = relationship(
        back_populates="history", lazy="selectin", cascade="all, delete-orphan", order_by="IdeaHistoryKnower.id")


class IdeaHistoryKnower(KnowerMixin, Base):
    """アイデアの履歴(呼び名)の行を知る相手。この行に当たる人物だけが履歴を知る(効く場所・期間に住んでいても、当たらなければ知らない)。"""

    __tablename__ = "idea_history_knower"
    __table_args__ = _knower_args("idea_history_knower", "idea_history_id")

    idea_history_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("idea_history.id"), index=True, nullable=False, sort_order=100)

    history: Mapped[IdeaHistory] = relationship(back_populates="knowers", lazy="noload")
    knower: Mapped["Character | None"] = relationship(lazy="noload")


class LocationHistoryKnower(KnowerMixin, Base):
    """場所の来歴の行を知る相手。この行に当たる人物だけが来歴を知る。"""

    __tablename__ = "location_history_knower"
    __table_args__ = _knower_args("location_history_knower", "location_history_id")

    location_history_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("location_history.id"), index=True, nullable=False, sort_order=100)

    history: Mapped[LocationHistory] = relationship(back_populates="knowers", lazy="noload")
    knower: Mapped["Character | None"] = relationship(lazy="noload")


def _subject_start(s: Session, row: KnowerMixin) -> Stamp | None:
    """知る相手の行の、知られる行の始まり。"""
    match row:
        case IdeaHistoryKnower():
            history = row.history or s.get(IdeaHistory, row.idea_history_id)
            return None if history is None else history.start
        case CharacterHistoryKnower():
            return (row.history or s.get_one(CharacterHistory, row.character_history_id)).start
        case CharacterSkillHistoryKnower():
            return (row.history or s.get_one(CharacterSkillHistory, row.character_skill_history_id)).start
        case LocationHistoryKnower():
            return (row.history or s.get_one(LocationHistory, row.location_history_id)).start
        case _:
            return None


def _knower_start(s: Session, row: KnowerMixin) -> Stamp | None:
    """知る人物なら生まれ。場所なら、知られる行の始まりか、場所のできた時刻。"""
    character = getattr(row, "knower", None) or (None if row.knower_id is None else s.get(Character, row.knower_id))
    if character is not None:
        return character.start
    location = None if row.location_id is None else s.get(Location, row.location_id)
    return _subject_start(s, row) or (None if location is None else location.start)


@event.listens_for(Session, "before_flush")
def _date_new_knowers(s: Session, _flush_context, _instances) -> None:
    """知った時刻を渡さずに足した・直した知る相手に、知った時刻を入れる。
    知った時刻の空いた行は人物役に読ませない(`data_access_logic/character/knowledge.py`)ので、空のまま書かない。"""
    for row in [*s.new, *s.dirty]:
        if isinstance(row, KnowerMixin) and row.start is None:
            row.start = _knower_start(s, row)


class Story(TextBase):

    __tablename__ = "story"

    TEXT_COLUMNS = ("text", "instruction")

    name: Mapped[str] = mapped_column(String, sort_order=200)
    display_order: Mapped[int | None] = mapped_column(
        Integer, comment="作品一覧で同じ親の作品の中の並び。小さいほど上。空の作品は後ろに、一番早い話の順",
        sort_order=210)

    parent_story_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("story.id"), comment="親の作品。章・外伝は親の作品の子にする", sort_order=270)
    # 章の話を書くとき、親の作品の筋書きまでたどって渡す。書き込みは常に parent_story_id を直に触る
    parent_story: Mapped["Story | None"] = relationship(remote_side="Story.id", viewonly=True)

    instruction: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default="",
        comment="この作品と子孫(章・外伝)の作品で AI が書くすべての文に足す指示。空なら何も足さない", sort_order=10010)

    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="story", lazy="noload",
        order_by="[Episode.start.asc().nulls_last(), Episode.id.asc()]")


class Episode(ContentBase):
    """話。プロット・時刻・視点・場所と本文、本文の概要までを一行に持つ。"""

    __tablename__ = "episode"

    TEXT_COLUMNS = ("plot_text", "main_text", "instruction")

    main_text: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default="",
        comment="本文。まだ書いていない話(枠だけ)は空文字", sort_order=10000)

    story_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("story.id"), comment="属する作品。章の話は章の作品に付け、書くときは親の作品の筋書きまでたどる",
        sort_order=200)
    story: Mapped[Story] = relationship(back_populates="episodes", lazy="noload")
    title: Mapped[str] = mapped_column(
        String,  comment="サブタイトル。本文の見出しから読む", sort_order=220)

    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="話が立つ時刻。作品の中の話はこの順に並ぶ(空の話は後ろに id 順)", sort_order=250)
    end: Mapped[Stamp | None] = mapped_column(StampType, sort_order=260)
    viewpoint_character_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("character.id"), comment="視点。誰に寄って語るか", sort_order=270)
    viewpoint_character: Mapped["Character | None"] = relationship(
        foreign_keys="Episode.viewpoint_character_id", lazy="noload")
    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"), comment="場所", sort_order=280)
    location: Mapped[Location | None] = relationship(
        foreign_keys="Episode.location_id", lazy="noload")

    episode_characters: Mapped[list["EpisodeCharacter"]] = relationship(
        back_populates="episode", lazy="noload", cascade="all, delete-orphan", order_by="EpisodeCharacter.id")

    letters: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="字数。本文から数える", sort_order=290)

    plot_text: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default="",
        comment="プロット。作者が入れる、AI 生成前の話の中身",
        sort_order=10010)
    instruction: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default="",
        comment="この話の本文・プロットを書くときに足す指示。空なら何も足さない", sort_order=10020)

    @validates("main_text")
    def _letters_follow_text(self, _key, value):
        self.letters = len(value or "")
        return value


class EpisodeCharacter(Base):
    __tablename__ = "episode_character"

    episode_id: Mapped[int] = mapped_column(Integer, ForeignKey("episode.id"), index=True, sort_order=100)
    character_id: Mapped[int] = mapped_column(Integer, ForeignKey("character.id"), index=True, sort_order=110)
    mentioned: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="この話に登場せず、プロット・本文に名前が出るだけの人物か。"
                "話の確定・プロット補完・枠の生成のたびに、プロット・本文から拾い直す",
        sort_order=120)

    episode: Mapped["Episode"] = relationship(back_populates="episode_characters", lazy="noload")
    character: Mapped["Character"] = relationship(lazy="noload")


# 読み書きする db の SQLAlchemy の URL。手元は踏み台越しの RDS(`tool.aws.rds --serve`)、Lambda は VPC の中の RDS、
# テストは手元の PostGIS(`tool.test`)を指す。web のセッションは db に繋がず表の定義だけを使うので、無くても import はできる
DATABASE_URL = os.environ.get("DEM_DATABASE_URL") or None
# RDS の IAM データベース認証で繋ぐか(パスワードの代わりに、接続のたびにトークンを作る)
DATABASE_IAM_AUTH = os.environ.get("DEM_DATABASE_IAM_AUTH") == "1"
# 手元の転送(127.0.0.1)越しに IAM 認証で繋ぐとき、トークンは RDS の本来のエンドポイントに宛てて作る。その在りかの SSM パラメータ
_RDS_ENDPOINT_PARAMETERS = ("/novel/db/endpoint", "/novel/db/port")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def seed_master_rows(engine) -> None:
    with Session(engine) as s:
        s.add_all(PersonalityLevelOption(id=id_, name=name)
                  for name, id_ in _PERSONALITY_LEVEL_IDS.items())
        s.commit()


def database_url() -> str:
    if not DATABASE_URL:
        raise RuntimeError("DEM_DATABASE_URL が無い。手元は `tool.aws.rds --serve` の転送と、"
                           "SessionStart フックか .vscode が渡す DEM_DATABASE_URL で RDS に繋ぐ(.claude/docs/setup.md)")
    return DATABASE_URL


def make_url_engine(url: str, iam_auth: bool = False):
    if make_url(url).get_backend_name() == "sqlite":
        return create_engine(url)
    # Lambda は凍結をはさんで接続を使い回し、手元の転送は 1 時間で張り直すので、切れた接続を使う前に確かめる
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=300)
    if iam_auth:
        _use_iam_auth_token(engine)
    return engine


def _use_iam_auth_token(engine) -> None:
    # RDS の IAM データベース認証のトークンは 15 分で切れるので、接続を張るたびに作る。
    # 署名は手元で作るので、NAT の無い VPC の中の Lambda からでも外へ出ずに済む。
    # トークンは rds-db の SigV4 の署名付き URL(boto3 の generate_db_auth_token と同じもの)。boto3 の client を作ると
    # rds のサービスの定義まで読み込み、Lambda のコールドスタートが延びるので、botocore の署名だけで作る
    import botocore.session
    from botocore.auth import SigV4QueryAuth
    from botocore.awsrequest import AWSRequest

    aws = botocore.session.get_session()
    region = aws.get_config_variable("region")
    signed_for: dict[tuple[str, int], tuple[str, int]] = {}

    def rds_endpoint(host: str, port: int) -> tuple[str, int]:
        if host not in _LOOPBACK_HOSTS:
            return host, port
        if (host, port) not in signed_for:
            import boto3

            values = boto3.client("ssm").get_parameters(Names=list(_RDS_ENDPOINT_PARAMETERS))["Parameters"]
            found = {value["Name"]: value["Value"] for value in values}
            endpoint, rds_port = (found[name] for name in _RDS_ENDPOINT_PARAMETERS)
            signed_for[(host, port)] = (endpoint, int(rds_port))
        return signed_for[(host, port)]

    @event.listens_for(engine, "do_connect")
    def _set_token(dialect, conn_rec, cargs, cparams):
        host, port = rds_endpoint(cparams["host"], int(cparams.get("port", 5432)))
        request = AWSRequest(method="GET", url=f"https://{host}:{port}/?Action=connect&DBUser={quote(cparams['user'])}")
        SigV4QueryAuth(aws.get_credentials().get_frozen_credentials(), "rds-db", region, expires=900).add_auth(request)
        cparams["password"] = str(request.url).removeprefix("https://")


def _no_database(*args, **kwargs):
    database_url()


# URL が無ければ、繋いだ時点で database_url() の理由で止まる engine にする
engine = (make_url_engine(DATABASE_URL, iam_auth=DATABASE_IAM_AUTH) if DATABASE_URL
          else create_engine("postgresql+psycopg://", creator=_no_database))


def get_env_session():
    return Session(engine)
