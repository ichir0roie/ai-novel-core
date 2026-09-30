#!/usr/bin/env python3
from __future__ import annotations

import enum
import hashlib
import os
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Integer, String, DECIMAL, JSON, TypeDecorator,
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


class ConfirmStatus(enum.StrEnum):
    """アイデア・ミームの `confirmed` 列の値。ユーザが確かめたかを三段で持つ。

    - 未確認: 本文から自動で足した直後の候補。検索・生成・人物へ引く対象に出ない
    - 承認: ユーザが確かめた。使ってよい
    - 非承認: ユーザが退けた。使わないが、同じ語をまた候補に足さないよう行は残す
    """
    PENDING = "未確認"
    APPROVED = "承認"
    REJECTED = "非承認"


CONFIRM_STATUSES = tuple(status.value for status in ConfirmStatus)

# 三段にする前の bool の書き方(true/false)からの読み替え
_CONFIRM_LEGACY = {True: ConfirmStatus.APPROVED, False: ConfirmStatus.PENDING,
                   "true": ConfirmStatus.APPROVED, "false": ConfirmStatus.PENDING,
                   "1": ConfirmStatus.APPROVED, "0": ConfirmStatus.PENDING}


def parse_confirm_status(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, ConfirmStatus):
        return value.value
    if isinstance(value, bool) or (isinstance(value, int) and value in (0, 1)):
        return _CONFIRM_LEGACY[bool(value)].value
    text = str(value).strip()
    if text in CONFIRM_STATUSES:
        return text
    legacy = _CONFIRM_LEGACY.get(text.lower())
    if legacy is not None:
        return legacy.value
    raise ValueError(f"confirmed は {'/'.join(CONFIRM_STATUSES)} のいずれか: {value!r}")


class ConfirmStatusType(TypeDecorator):
    """`confirmed` 列。db には値の文字列(未確認/承認/非承認)で持ち、以前の bool も受け取る。"""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return parse_confirm_status(value)

    def process_result_value(self, value, dialect):
        # マイグレーション前の db(1/0)を読んでも落ちないよう、読むときも読み替える
        try:
            return parse_confirm_status(value)
        except ValueError:
            return value


class Base(DeclarativeBase):

    # SQLite は「INTEGER PRIMARY KEY」だけを rowid の別名として autoincrement する。
    # Integer だと型名が INTEGER と一致せず insert のたびに id が NULL のまま失敗する。
    # sort_order は列の並び順を明示するための番号。継承の段が一段深くなるごとに
    # 開始値を 100 増やし、同じクラス内では 10 刻みで振る(あとで列を挟みやすい)。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, sort_order=0)


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
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("location.id"), sort_order=220)

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

    active_random_generation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 自分の親(一つ上の場所)。木をのぼって道筋(location_path)を組むのに使う。
    # 書き込みは常に parent_id を直に触るので、どちらも読み取り専用にしておく
    # (viewonly を外すと、同じ外部キーを double-write しようとして SQLAlchemy が警告する)。
    parent: Mapped["Location | None"] = relationship(
        remote_side="Location.id", viewonly=True, lazy="noload")
    children: Mapped[list[Location]] = relationship(viewonly=True)


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


class Event(EventSeededMixin, MemeSeededMixin, TextBase):

    __tablename__ = "event"

    name: Mapped[str] = mapped_column(String, sort_order=200)
    # 断面(ReadBrief)に出すかどうかだけを持つ。分類は name/text の書き方で表す。
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, sort_order=210)
    confirmed: Mapped[str] = mapped_column(
        ConfirmStatusType, default=ConfirmStatus.APPROVED, nullable=False,
        comment=f"ユーザが確かめた出来事として使ってよいか。{'/'.join(CONFIRM_STATUSES)} のいずれか。"
                "ランダム生成の直後は 未確認 で、話・筋書きには使われない。"
                "確かめたら 承認、無かったことにするなら 非承認 にする",
        sort_order=215)
    time: Mapped[Stamp] = mapped_column(StampType, index=True, sort_order=220)

    parent_event_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("event.id"), sort_order=230)

    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"), index=True, sort_order=240)
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
    """ミームは移り変わり・伝染していくものなので、どの元から抜き出したか、どの人物が持つかは持たない
    (元の側の `meme_seeded` で、抜き出し済みかだけを管理する)。
    """

    __tablename__ = "meme"

    category: Mapped[str | None] = mapped_column(
        String, nullable=True,
        comment=f"分類。{'/'.join(MEME_CATEGORIES)} のいずれか。空なら次の抽出で AI が振る",
        sort_order=200)
    confirmed: Mapped[str] = mapped_column(
        ConfirmStatusType, default=ConfirmStatus.PENDING, nullable=False,
        comment=f"ユーザが確かめた考え方として使ってよいか。{'/'.join(CONFIRM_STATUSES)} のいずれか。"
                "本文から自動で抜き出した直後は 未確認 で、人物へ引く・書き込む対象に出ない。"
                "レビューで確かめたら 承認、退けたら 非承認 にする",
        sort_order=205)


class Oracle(MemeSeededMixin, TextBase):
    """著者自身の創作・AI についての覚え書き。物語のデータではない。"""

    __tablename__ = "oracle"

    title: Mapped[str | None] = mapped_column(String, comment="題。覚え書きを呼ぶ名前", sort_order=200)


class StylePreference(TextBase):
    """世界ごとの文体の好み(舞台設定・既存の話から抽出した文体の癖)。`ai/instructions/style.py` の固定の文面に足して AI に渡す。"""

    __tablename__ = "style_preference"

    target: Mapped[str] = mapped_column(
        String, nullable=False, unique=True,
        comment="効く対象。shared はどの対象にも効き、episode などはその対象(`ai/instructions/style.py` の STYLE_BASES)だけに効く",
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


class Character(EventSeededMixin, MemeSeededMixin, TextBase):
    """人物に限らず、国・組織・集団・物も一行として持つ(`kind` で区別)。

    ミームは人物どうしで移り変わり・伝染していくものなので、`Meme` 側との FK は持たない。
    """

    __tablename__ = "character"

    text: Mapped[str | None] = mapped_column(String, nullable=True, sort_order=10000)

    name: Mapped[str | None] = mapped_column(String, sort_order=210)
    kind: Mapped[str] = mapped_column(
        String, default=CHARACTER_KIND_PERSON, nullable=False,
        comment="種別。「人物」か、人物以外の対象(国・組織・商会・氏族・集団・物など)", sort_order=230)
    confirmed: Mapped[str] = mapped_column(
        ConfirmStatusType, default=ConfirmStatus.APPROVED, nullable=False,
        comment=f"ユーザが確かめた人物・対象として使ってよいか。{'/'.join(CONFIRM_STATUSES)} のいずれか。"
                "ランダム生成の直後は 未確認 で、話・筋書きには使われない。"
                "確かめたら 承認、無かったことにするなら 非承認 にする",
        sort_order=235)

    main_character: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="メインキャラクターか。"
        "出来事・筋書きのランダム生成は、この列が false(サブキャラクター)の人物・対象だけを対象にする",
        sort_order=240)

    # 出自(生まれの場所)は別列を持たず、CharacterLocation の一番古い行として表す。
    # 名字・体格・口調・性格は期間ごとに CharacterParameter が、居場所は期間ごとに CharacterLocation が持ち、
    # 入口では `parameters` / `locations` の配列で出し入れする。誕生・死亡も専用の列を持たず、
    # `parameters` の一番早く始まる行の start・一番後に始まる行の end として表す(下の `start` / `end`)。
    # 人物の説明の変化は期間ごとに CharacterHistory が持ち、入口では `histories` の配列で出し入れする
    # (Idea の `recognitions` と同じ扱い)。
    CHILD_LISTS = ("parameters", "locations", "histories")
    def _last_parameter(self) -> "CharacterParameter | None":
        if not self.parameters:
            return None
        bounded = [(row.start, row) for row in self.parameters if row.start is not None]
        return max(bounded, key=lambda pair: pair[0])[1] if bounded else self.parameters[-1]

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

    @property
    def end(self) -> Stamp | None:
        """死亡。`parameters` の一番後に始まる行(=今も効いている行)の end。"""
        last = self._last_parameter()
        return last.end if last else None

    @end.setter
    def end(self, value) -> None:
        last = self._last_parameter()
        if last is None:
            last = CharacterParameter()
            self.parameters.append(last)
        last.end = Stamp.parse(value)

    # relationships

    parameters: Mapped[list[CharacterParameter]] = relationship(
        back_populates="character", lazy="selectin", cascade="all, delete-orphan",
        order_by="CharacterParameter.id")
    locations: Mapped[list[CharacterLocation]] = relationship(
        back_populates="character", lazy="selectin", cascade="all, delete-orphan",
        order_by="CharacterLocation.start.desc().nulls_last()"
    )
    histories: Mapped[list["CharacterHistory"]] = relationship(
        back_populates="character", lazy="selectin", cascade="all, delete-orphan",
        order_by="CharacterHistory.start.desc().nulls_last()"
    )
    events: Mapped[list[Event]] = relationship(
        secondary="event_character", viewonly=True, lazy="noload",
        order_by="Event.start.desc().nulls_last()"
    )


class CharacterParameter(Base):
    """人物の名字・体格・口調・性格を、期間ごとに一行で持つ。

    空の列は「この期間では決めない」。ある時刻の値は `data_access_logic/character/parameters.py` の `parameters_at` が、その時刻に掛かる行を
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

    def covers(self, time: Stamp | None) -> bool:
        """時刻が空なら、期間を限らない行だけが掛かる。"""
        if time is None:
            return self.start is None and self.end is None
        return (self.start is None or self.start <= time) and (self.end is None or time < self.end)


class CharacterLocation(Base):

    __tablename__ = "character_location"

    character_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("character.id"), sort_order=100)
    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("location.id"), sort_order=110)

    start: Mapped[Stamp | None] = mapped_column(StampType, sort_order=120)
    end: Mapped[Stamp | None] = mapped_column(StampType, sort_order=130)

    character: Mapped[Character | None] = relationship(back_populates="locations", lazy="noload")
    location: Mapped[Location] = relationship(lazy="noload")


class CharacterRelation(TextBase):
    """`character_1_id` から見た `character_2_id` との関係を一行で持つ。"""

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


class CharacterHistory(Base):
    """人物の説明(来歴)を、期間ごとの一行で持つ。`IdeaRecognition` と同じ扱いの子テーブル。

    `character.text` 自体は書き換えず、時が進むにつれて変わった立場・境遇などを
    `start` から `end` の手前までの期間ごとに `description` として積む。
    """

    __tablename__ = "character_history"

    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("character.id"), index=True, nullable=False, sort_order=100)
    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="この説明が効き始める時。空なら始まりを限らない", sort_order=110)
    end: Mapped[Stamp | None] = mapped_column(
        StampType, comment="この説明が効き終わる時(この時からは効かない)。空なら終わりを限らない", sort_order=120)
    description: Mapped[str] = mapped_column(String, nullable=False, comment="この期間での説明", sort_order=130)

    character: Mapped[Character] = relationship(back_populates="histories", lazy="noload")


class Idea(MemeSeededMixin, TextBase):
    __tablename__ = "idea"

    name: Mapped[str] = mapped_column(String, sort_order=200)
    kind: Mapped[str] = mapped_column(String, comment="種別(技術・制度・概念など)", sort_order=210)
    confirmed: Mapped[str] = mapped_column(
        ConfirmStatusType, default=ConfirmStatus.APPROVED, nullable=False,
        comment=f"確かめた設定として使ってよいか。{'/'.join(CONFIRM_STATUSES)} のいずれか。"
                "本文から自動で足した候補は 未確認 で、検索・生成には出ない。"
                "確かめたら 承認、設定ではないと退けたら 非承認 にする",
        sort_order=215)

    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"), index=True,
        comment="効く場所。この場所とその配下で効く。空ならどこにも効かない", sort_order=220)
    start: Mapped[Stamp | None] = mapped_column(
        StampType, comment="効き始める時刻。出来事の時刻と比べる。空なら始まりを限らない", sort_order=230)
    end: Mapped[Stamp | None] = mapped_column(
        StampType, comment="効き終わる時刻(この時刻からは効かない)。空なら終わりを限らない", sort_order=240)

    parent_idea_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("idea.id"), comment="上位のアイデア", sort_order=250)

    # 場所・時代ごとの作中での呼び名は IdeaRecognition で積む。GUI では recognitions に並ぶ。
    CHILD_LISTS = ("recognitions",)

    recognitions: Mapped[list["IdeaRecognition"]] = relationship(
        back_populates="idea", lazy="selectin", cascade="all, delete-orphan",
        order_by="IdeaRecognition.start.desc().nulls_last()")


class IdeaRecognition(Base):
    """アイデアの作中での呼び名を、場所・時代ごとに一行で持つ。

    `location_id` の場所とその配下、`start` から `end` の手前までのあいだ効き、空の列はどこでも・いつでも効く。
    当てはまる行が無ければ本質の `name` をそのまま使う(`data_access_logic/idea/alias.py` の `called`)。
    効く場所・時代にいる人物は、この名前でアイデアを認識している前提で本文を書く(`ai/instructions/idea_context.py`)。
    """

    __tablename__ = "idea_recognition"

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
    detail: Mapped[str | None] = mapped_column(String, comment="呼び名についての注釈(作中での受け止め方)", sort_order=150)

    idea: Mapped[Idea] = relationship(back_populates="recognitions", lazy="noload")


class Story(EventSeededMixin, TextBase):

    __tablename__ = "story"

    name: Mapped[str] = mapped_column(String, sort_order=200)

    world_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"), comment="使用する世界線", sort_order=210)
    world: Mapped[Location | None] = relationship(
        foreign_keys="Story.world_id", lazy="noload")
    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("location.id"), comment="立つ場所。断面を取るのに使う", sort_order=220)
    location: Mapped[Location | None] = relationship(
        foreign_keys="Story.location_id", lazy="noload")
    narration: Mapped[str] = mapped_column(String,  comment="語り", sort_order=230)
    state: Mapped[str] = mapped_column(String,  comment="状態", sort_order=240)

    start: Mapped[Stamp | None] = mapped_column(StampType, comment="立つ年", sort_order=250)
    end: Mapped[Stamp | None] = mapped_column(StampType, sort_order=260)

    parent_story_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("story.id"), comment="親の作品。章・外伝は親の作品の子にする", sort_order=270)
    # 章の話を書くとき、親の作品の筋書きまでたどって渡す。書き込みは常に parent_story_id を直に触る
    parent_story: Mapped["Story | None"] = relationship(remote_side="Story.id", viewonly=True)

    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="story", lazy="noload",
        order_by="[Episode.start.asc().nulls_last(), Episode.id.asc()]")


class Episode(EventSeededMixin, ContentBase):
    """話。プロット・時刻・視点・場所と本文、本文の概要までを一行に持つ。"""

    __tablename__ = "episode"

    TEXT_COLUMNS = ("plot_text", "main_text")

    main_text: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default="",
        comment="本文。まだ書いていない話(枠だけ)は空文字", sort_order=10000)

    story_id: Mapped[int] = mapped_column(Integer, ForeignKey("story.id"), sort_order=200)
    story: Mapped[Story] = relationship(back_populates="episodes", lazy="noload")
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
    summary_text: Mapped[str | None] = mapped_column(
        String, comment="本文の概要。AI が本文から作る。まだ作っていなければ空", sort_order=10020)
    summary_source_hash: Mapped[str | None] = mapped_column(
        String, comment="概要を作った本文の sha256。本文と食い違ったら概要を作り直す", sort_order=10030)

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
                "推敲・プロット補完・枠の生成のたびに、プロット・本文から拾い直す",
        sort_order=120)

    episode: Mapped["Episode"] = relationship(back_populates="episode_characters", lazy="noload")
    character: Mapped["Character"] = relationship(lazy="noload")


class EventIdea(Base):
    """出来事の本文が踏まえたアイデア。"""

    __tablename__ = "event_idea"
    __table_args__ = (UniqueConstraint("event_id", "idea_id"),)

    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("event.id"), index=True, sort_order=100)
    idea_id: Mapped[int] = mapped_column(Integer, ForeignKey("idea.id"), index=True, sort_order=110)


class EpisodeIdea(Base):
    """話のプロットから引いて本文が踏まえたアイデア。"""

    __tablename__ = "episode_idea"
    __table_args__ = (UniqueConstraint("episode_id", "idea_id"),)

    episode_id: Mapped[int] = mapped_column(Integer, ForeignKey("episode.id"), index=True, sort_order=100)
    idea_id: Mapped[int] = mapped_column(Integer, ForeignKey("idea.id"), index=True, sort_order=110)


class CharacterIdea(Base):
    """人物・対象の説明が踏まえたアイデア。"""

    __tablename__ = "character_idea"
    __table_args__ = (UniqueConstraint("character_id", "idea_id"),)

    character_id: Mapped[int] = mapped_column(Integer, ForeignKey("character.id"), index=True, sort_order=100)
    idea_id: Mapped[int] = mapped_column(Integer, ForeignKey("idea.id"), index=True, sort_order=110)


def utc_now() -> datetime:
    # SQLite の DateTime は時差を持てないので、どちらの db でも時差を落とした UTC で持つ
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AiTaskStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class AiTask(Base):
    """claude を叩く入口の呼び出しを、後で Claude Code on the web のセッションが拾って回すための待ち行列。

    claude の無い環境(Lambda の API)で「AI で作成」などを押すと、呼び出しをここに積むだけで返す
    (`gui/api/claude_env.py` の `queue` モード)。`web_session/run_ai_tasks.py` が古い順に拾って回す。
    """

    __tablename__ = "ai_task"

    entrance: Mapped[str] = mapped_column(
        String, nullable=False, comment="呼ぶ入口(`gui/api/interface.py` の id。例: episode.generate_episode.GenerateEpisode)",
        sort_order=100)
    args: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="入口に渡す引数(JSON)", sort_order=110)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=AiTaskStatus.QUEUED, index=True,
        comment="queued / running / done / failed", sort_order=120)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="拾った回数。回したセッションが途中で止まって拾い直すたびに増え、上限を超えたら failed にする", sort_order=125)
    result: Mapped[dict | list | None] = mapped_column(JSON(none_as_null=True), comment="入口の結果(JSON)", sort_order=130)
    error: Mapped[str | None] = mapped_column(String, comment="落ちた理由", sort_order=140)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, sort_order=160)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, sort_order=180)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, sort_order=190)


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
    # 署名は手元で作るので、NAT の無い VPC の中の Lambda からでも外へ出ずに済む
    import boto3
    from sqlalchemy import event

    rds = boto3.client("rds")
    signed_for: dict[tuple[str, int], tuple[str, int]] = {}

    def rds_endpoint(host: str, port: int) -> tuple[str, int]:
        if host not in _LOOPBACK_HOSTS:
            return host, port
        if (host, port) not in signed_for:
            values = boto3.client("ssm").get_parameters(Names=list(_RDS_ENDPOINT_PARAMETERS))["Parameters"]
            found = {value["Name"]: value["Value"] for value in values}
            endpoint, rds_port = (found[name] for name in _RDS_ENDPOINT_PARAMETERS)
            signed_for[(host, port)] = (endpoint, int(rds_port))
        return signed_for[(host, port)]

    @event.listens_for(engine, "do_connect")
    def _set_token(dialect, conn_rec, cargs, cparams):
        host, port = rds_endpoint(cparams["host"], int(cparams.get("port", 5432)))
        cparams["password"] = rds.generate_db_auth_token(
            DBHostname=host, Port=port, DBUsername=cparams["user"], Region=rds.meta.region_name)


def _no_database(*args, **kwargs):
    database_url()


# URL が無ければ、繋いだ時点で database_url() の理由で止まる engine にする
engine = (make_url_engine(DATABASE_URL, iam_auth=DATABASE_IAM_AUTH) if DATABASE_URL
          else create_engine("postgresql+psycopg://", creator=_no_database))


def get_env_session():
    return Session(engine)
