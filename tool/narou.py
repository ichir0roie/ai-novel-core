#!/usr/bin/env python3
"""話の本文を、Playwright で小説家になろうへ投稿する。手元だけで動かす(web のセッションでは止まる)。

ブラウザは、ワークスペースの `.cache/narou/browser/` をユーザデータのディレクトリにして開く。
ログインは最初に一度だけ人が手で行い、そのクッキーがこのディレクトリに残る。以後の操作はそれでログイン済みとして動く。
クッキーが切れていたら `login` からやり直す。

    .venv/bin/python -m tool.narou login                          # ブラウザが開くので、手でログインする
    .venv/bin/python -m tool.narou post --episode 61              # 確認画面まで進め、スクショを撮って止まる
    .venv/bin/python -m tool.narou post --episode 61 --submit     # 確認画面から投稿まで押す
    .venv/bin/python -m tool.narou outdated                       # 投稿のあとに直した(なろうが古い)話を出す
    .venv/bin/python -m tool.narou link --episode 61 --part 123   # 話に部分の番号を手で結ぶ(unlink で外す)
    .venv/bin/python -m tool.narou match-novels [--apply]         # なろうの小説を作品に当てはめる
    .venv/bin/python -m tool.narou match-parts [--story 3] [--apply]  # なろうの部分を話に当てはめる

`match-*` は、なろうの一覧と db の行を題で突き合わせた案を JSON で出す。`--apply` を付けると、案のとおりに番号を書く。

投稿先の小説は、話の作品(章・外伝なら番号のある一番近い親の作品)の `story.narou_novel_id`。
話と部分の結び(部分の番号と、最後に投稿・書き換えた時刻)は表 `narou_part` に持ち、話の行には書かない。
まだ投稿していない話(結びが無い)は次話として足し、結びを書く。投稿した話は、その部分を今の題・本文で書き換える。
書き換えるのは、投稿のあとに話を直した(話の `updated_at` が投稿した時刻より新しい)ときだけ(`--force` で、直していなくても書き換える)。
playwright は `requirements-narou.txt` で入れ、初めて動かす手元では、ブラウザを
`.venv/bin/python -m playwright install chromium` で入れておく。

画面の URL・入力欄・ボタン(下の定数)は、2026-10 のなろうの画面と突き合わせてある。一覧のページ送り(`NEXT_PAGE_LINK`)だけは未確認。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from data_access_logic.logs import configure_logging
from data_access_logic.query import common_query
from data_access_logic.story.form import StoryUpdateForm
from data_access_logic.story.update_story import UpdateStory
from db.schema import Episode, NarouPart, Story, get_env_session

logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "narou"
# ブラウザのユーザデータ(クッキー・履歴)。ワークスペースに置き、なろうの操作はいつもこれで開く
USER_DATA_DIR = STATE_DIR / "browser"

LOGIN_URL = "https://ssl.syosetu.com/login/input/"
NOVEL_LIST_URL = "https://syosetu.com/usernovel/list/"
NOVEL_URL = "https://syosetu.com/usernovelmanage/top/ncode/{novel}/"
# 新しいエピソードは下書きとして足してから投稿する作り。編集は確認の画面を経て保存する
NEW_PART_URL = "https://syosetu.com/draftepisode/input/ncode/{novel}/"
EDIT_URL = "https://syosetu.com/usernoveldatamanage/updateinput/ncode/{novel}/noveldataid/{part}/"
NOVEL_ID_PATTERN = re.compile(r"/usernovelmanage/top/ncode/(\d+)")
# 部分の一覧で読むのは部分の管理画面へのリンク。同じ部分を指す編集(updateinput)のリンクは拾わない
PART_LINK_PATTERN = re.compile(r"/usernoveldatamanage/top/ncode/\d+/noveldataid/(\d+)")
# 一覧のリンクの題。「連載」「ep.1」「代表作」などの印は span に入るので、リンクの直下の文字だけを読む
LINK_TITLE_SCRIPT = ("e => [...e.childNodes].filter(n => n.nodeType === Node.TEXT_NODE)"
                     ".map(n => n.textContent).join('')")
# 一覧がページに分かれるときの、次のページへのリンクの文言(75 部分では分かれず、未確認)
NEXT_PAGE_LINK = "次へ"
SUBTITLE_FIELD = "input[name='subtitle']"
TEXT_FIELD = "textarea[name='novel']"
# 編集: 入力の画面 →「保存[確認]」→ 確認の画面(updateconfirm)→「保存[実行]」
EDIT_CONFIRM_BUTTON = "input[type='submit'][value='保存[確認]']"
EDIT_SUBMIT_BUTTON = "input[type='submit'][value='保存[実行]']"
# 新しいエピソード: 入力の画面 →「下書き保存」→ 下書きの画面の「投稿」で重ねる窓(postinput)→「投稿[確認]」
# → 確認の窓(postconfirm)→「投稿[実行]」→ 終わりの窓(postend)。窓の中身は開いたときに読み込まれる
SAVE_DRAFT_BUTTON = "input[type='submit'][value='下書き保存']"
DRAFT_POST_LINK = "a.c-button--primary:text-is('投稿')"
POST_CONFIRM_BUTTON = ".js-post_confirm_button"
POST_BUTTON = ".js-post_button"
POST_MODAL = ".remodal[data-remodal-id='{name}']"
# 窓の中身が読み込まれるのを待つ長さ
MODAL_TIMEOUT_MS = 15 * 1000

# 手でログインし終えるのを待つ長さ
LOGIN_TIMEOUT_MS = 10 * 60 * 1000
# 画面の操作の前に置く間。なろうへの負荷を下げる
OPERATION_INTERVAL_SECONDS = 1.0


@dataclass
class Post:
    episode_id: int
    novel_id: int
    # 投稿した部分の番号。まだ投稿していなければ None
    novel_data_id: int | None
    subtitle: str
    text: str


def ensure_local() -> None:
    # web のセッションのコンテナにはクッキーを置かず、本番の作品をそこから外へ出さない
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        raise SystemExit("なろうへの投稿は手元だけで動かす。web のセッションでは動かさない")


def is_login_page(url: str) -> bool:
    return "/login/" in url


class Site:
    """なろうの画面の操作。画面に触れる操作はみなここを通し、間を置いてから行い、読み込みを待つ。

    `logged_in` なら、操作のあとにログインの画面へ飛ばされていないかも確かめる(ログインの操作だけが外す)。
    """

    def __init__(self, page: Page, logged_in: bool = True):
        self.page = page
        self.logged_in = logged_in

    def _operate(self, action: Callable[[], object]) -> None:
        time.sleep(OPERATION_INTERVAL_SECONDS)
        action()
        self.page.wait_for_load_state()
        if self.logged_in and is_login_page(self.page.url):
            raise SystemExit("ログインが切れている。`python -m tool.narou login` でやり直す")

    def goto(self, url: str) -> None:
        self._operate(lambda: self.page.goto(url))

    def click(self, selector: str) -> None:
        self._operate(lambda: self.page.click(selector))

    def click_link(self, name: str) -> None:
        self._operate(lambda: self.page.get_by_role("link", name=name).first.click())

    def fill(self, selector: str, text: str) -> None:
        self._operate(lambda: self.page.fill(selector, text))


def part_of(s: Session, episode_id: int) -> NarouPart | None:
    """話を投稿した部分。まだ投稿していなければ None"""
    return s.scalar(select(NarouPart).where(NarouPart.episode_id == episode_id))


def read_post(episode_id: int, force: bool) -> Post:
    """`force` でなければ、投稿のあとに直していない話(なろうが最新)は書き換えずに止める。"""
    with get_env_session() as s:
        episode = s.get(Episode, episode_id)
        if episode is None:
            raise SystemExit(f"話 {episode_id} が無い")
        if not episode.main_text.strip():
            raise SystemExit(f"話 {episode_id} に本文が無い")
        if not (episode.title or "").strip():
            raise SystemExit(f"話 {episode_id} に題(サブタイトル)が無い")
        part = part_of(s, episode_id)
        if part is not None and not force and episode.updated_at <= part.posted_at:
            raise SystemExit(f"話 {episode_id} は投稿({local_time(part.posted_at)})のあとに直していない。"
                             "なろうは最新なので書き換えない(書き換えるなら --force)")
        return Post(episode_id=episode.id, novel_id=novel_id_of(s, episode.story_id),
                    novel_data_id=part.novel_data_id if part else None, subtitle=episode.title, text=episode.main_text)


def novel_id_of(s: Session, story_id: int) -> int:
    """作品から親へたどって、最初に見つかった小説の番号。"""
    for path_id in reversed(common_query.story_path_ids(s, story_id)):
        novel_id = common_query.get_row(s, Story, path_id).narou_novel_id
        if novel_id is not None:
            return novel_id
    raise SystemExit(f"作品 {story_id} にも親の作品にも、なろうの小説の番号(narou_novel_id)が無い。GUI の作品の画面で入れる")


def novel_episodes(s: Session, novel_id: int) -> list[Episode]:
    """この小説へ投稿する話(番号を持つ作品と、番号の無い子孫の作品の話)。start 順"""
    story_ids = {story_id
                 for owner_id in s.scalars(select(Story.id).where(Story.narou_novel_id == novel_id))
                 for story_id in common_query.descendant_story_ids(s, owner_id)
                 if novel_id_of(s, story_id) == novel_id}
    return list(s.scalars(select(Episode).where(Episode.story_id.in_(story_ids))
                          .order_by(Episode.start.asc().nulls_last(), Episode.id.asc())))


def record_posted(s: Session, episode_id: int, novel_data_id: int) -> None:
    """話を部分として投稿・書き換えたこと(部分の番号と今の時刻)を結びの表に書く。話の行(updated_at)には触れない。"""
    s.execute(insert(NarouPart).values(episode_id=episode_id, novel_data_id=novel_data_id, posted_at=func.now())
              .on_conflict_do_update(index_elements=[NarouPart.episode_id],
                                     set_={"novel_data_id": novel_data_id, "posted_at": func.now()}))


def save_posted(episode_id: int, novel_data_id: int) -> None:
    with get_env_session() as s, s.begin():
        common_query.get_row(s, Episode, episode_id)
        record_posted(s, episode_id, novel_data_id)


def unlink_part(episode_id: int) -> None:
    """話と部分の結びを外す(なろうで部分を消したときなど)。"""
    with get_env_session() as s, s.begin():
        s.execute(delete(NarouPart).where(NarouPart.episode_id == episode_id))


def outdated_episodes() -> list[dict]:
    """なろうに投稿した話のうち、投稿のあとに直した(なろうが古い)話。直した順。本文の無い話は書き換えられないので外す。"""
    with get_env_session() as s:
        rows = s.execute(select(Episode, NarouPart).join(NarouPart, NarouPart.episode_id == Episode.id)
                         .where(Episode.main_text != "", Episode.updated_at > NarouPart.posted_at)
                         .order_by(Episode.updated_at))
        return [{"id": episode.id, "題": episode.title, "なろうの番号": part.novel_data_id,
                 "直した時刻": local_time(episode.updated_at), "投稿した時刻": local_time(part.posted_at)}
                for episode, part in rows.tuples()]


def local_time(moment: datetime) -> str:
    """db の時刻(UTC で返る)を、手元の時刻帯で秒まで出す。"""
    return moment.astimezone().isoformat(sep=" ", timespec="seconds")


@contextmanager
def open_site(headed: bool, logged_in: bool = True) -> Iterator[Site]:
    """ワークスペースのユーザデータのディレクトリでブラウザを開く。ログインのクッキーもそこに残り、次に開いても保たれる。"""
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        USER_DATA_DIR.chmod(0o700)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(USER_DATA_DIR, headless=not headed)
        try:
            yield Site(context.pages[0] if context.pages else context.new_page(), logged_in=logged_in)
        finally:
            # 閉じてから、ユーザデータ(クッキー)がディレクトリに書き切られる
            context.close()


def login() -> None:
    with open_site(headed=True, logged_in=False) as site:
        site.goto(LOGIN_URL)
        logger.info("ブラウザでなろうに「ログイン状態を保持」を付けてログインし、終えたら窓を閉じる(%d 分待つ)",
                    LOGIN_TIMEOUT_MS // 60000)
        # ログインの画面を離れた所で閉じると、ログインの途中の画面で閉じてしまうことがあるので、人が閉じるまで待つ
        site.page.wait_for_event("close", timeout=LOGIN_TIMEOUT_MS)
    logger.info("ログインのクッキーを %s に残した", USER_DATA_DIR)


def fill_form(site: Site, post: Post) -> None:
    """新しいエピソードか編集の入力の画面を開いてサブタイトルと本文を入れる。編集は確認の画面まで進める。

    新しいエピソードは、次の「下書き保存」でなろうに下書きが残るので、入れたところで止める。
    """
    if post.novel_data_id is None:
        site.goto(NEW_PART_URL.format(novel=post.novel_id))
    else:
        site.goto(EDIT_URL.format(novel=post.novel_id, part=post.novel_data_id))
    site.fill(SUBTITLE_FIELD, post.subtitle)
    site.fill(TEXT_FIELD, post.text)
    if post.novel_data_id is not None:
        site.click(EDIT_CONFIRM_BUTTON)


@dataclass
class Listed:
    """なろうの一覧に並ぶ小説か部分。"""
    id: int
    title: str


def listed_links(site: Site, url: str, pattern: re.Pattern[str]) -> list[Listed]:
    """一覧の画面を開き、`pattern` で番号の取れるリンクを並びの順に読む。次のページがあればたどる。"""
    site.goto(url)
    listed: dict[int, Listed] = {}
    while True:
        found = len(listed)
        for link in site.page.locator("a[href]").all():
            match = pattern.search(link.get_attribute("href") or "")
            if match is None:
                continue
            if int(match[1]) not in listed:
                # 題の前の印との間は &nbsp; で空くので、strip で落とす
                title = str(link.evaluate(LINK_TITLE_SCRIPT)).strip()
                listed[int(match[1])] = Listed(id=int(match[1]), title=title)
        # 最後のページにも「次へ」が残る作りでも止まるよう、新しい番号が無ければ終える
        if len(listed) == found or site.page.get_by_role("link", name=NEXT_PAGE_LINK).count() == 0:
            return list(listed.values())
        site.click_link(NEXT_PAGE_LINK)


def posted_novel_data_id(site: Site, post: Post) -> int | None:
    """小説の管理画面の部分の一覧から、足した部分の番号を読む。"""
    parts = listed_links(site, NOVEL_URL.format(novel=post.novel_id), PART_LINK_PATTERN)
    # 同じ題の部分があれば、一番新しく足したもの
    return max((part.id for part in parts if part.title == post.subtitle), default=None)


def open_modal(site: Site, button: str, name: str) -> str:
    """ボタンを押して重ねる窓を開き、中身が読み込まれるのを待って、窓の文字を返す。"""
    site.click(button)
    modal = POST_MODAL.format(name=name)
    site.page.wait_for_selector(f"{modal} :is(button, a, input)", state="visible", timeout=MODAL_TIMEOUT_MS)
    return site.page.inner_text(modal)


def post_draft(site: Site, post: Post) -> None:
    """入力の画面から下書きに保存し、下書きの画面の窓を進めて投稿する。予約・割り込み・完結は既定(しない)のまま。"""
    site.click(SAVE_DRAFT_BUTTON)
    logger.info("下書きに保存した: %s", site.page.url)
    open_modal(site, DRAFT_POST_LINK, "postinput")
    confirm = open_modal(site, POST_CONFIRM_BUTTON, "postconfirm")
    # 予約掲載の話が残っているときなどは、投稿のボタンの代わりに断りの文が出る(下書きはなろうに残る)
    if "エラー" in confirm:
        raise SystemExit(f"なろうが投稿を受け付けなかった: {' '.join(confirm.split())}")
    end = open_modal(site, POST_BUTTON, "postend")
    if "投稿が完了しました" not in end:
        raise SystemExit(f"投稿の終わりの窓が思っていた形でない: {' '.join(end.split())}")


def submit_form(site: Site, post: Post) -> None:
    """投稿まで押す。編集なら保存し、新しいエピソードなら投稿して部分の番号を話に書き戻す。"""
    if post.novel_data_id is not None:
        site.click(EDIT_SUBMIT_BUTTON)
        if "updateend" not in site.page.url:
            raise SystemExit(f"書き換えの保存が終わらなかった: {site.page.url}")
        save_posted(post.episode_id, post.novel_data_id)
        logger.info("話 %d で、小説 %d の部分 %d を書き換えた", post.episode_id, post.novel_id, post.novel_data_id)
        return
    post_draft(site, post)
    novel_data_id = posted_novel_data_id(site, post)
    if novel_data_id is None:
        logger.warning("話 %d を小説 %d に投稿したが、部分の番号が読めなかった。部分の管理画面の URL の noveldataid を、"
                       "`python -m tool.narou link --episode %d --part <番号>` で結ぶ",
                       post.episode_id, post.novel_id, post.episode_id)
        return
    save_posted(post.episode_id, novel_data_id)
    logger.info("話 %d を小説 %d の部分 %d として投稿した", post.episode_id, post.novel_id, novel_data_id)


def post_episode(episode_id: int, submit: bool, force: bool, headed: bool) -> None:
    post = read_post(episode_id, force)
    screenshot = STATE_DIR / f"episode-{episode_id}-confirm.png"
    with open_site(headed) as site:
        fill_form(site, post)
        site.page.screenshot(path=screenshot, full_page=True)
        logger.info("確認画面のスクショ: %s", screenshot)
        if submit:
            submit_form(site, post)
        else:
            logger.info("確認画面で止めた(投稿するなら --submit を付けて回し直す)")


@dataclass
class Row:
    """当てはめる db の行(作品か話)。"""
    id: int
    title: str
    narou_id: int | None


def pair_by_title(rows: list[Row], listed: list[Listed]) -> dict[str, list[dict]]:
    """db の行となろうの一覧を題で組む。同じ題がいくつもあれば、両方の並びの順に組む。

    番号の入っている行はそのまま残し、番号の無い行と、どの行にも当たっていない番号とを組んで案にする。
    """
    listed_ids = {item.id for item in listed}
    taken = {row.narou_id for row in rows if row.narou_id is not None}
    rows_by_title: defaultdict[str, list[Row]] = defaultdict(list)
    for row in rows:
        if row.narou_id is None:
            rows_by_title[row.title.strip()].append(row)
    pairs, unmatched_listed = [], []
    for item in listed:
        if item.id in taken:
            continue
        waiting = rows_by_title.get(item.title)
        if waiting:
            pairs.append({"id": waiting.pop(0).id, "題": item.title, "なろうの番号": item.id})
        else:
            unmatched_listed.append({"なろうの番号": item.id, "題": item.title})
    return {
        "当てはめる": pairs,
        "番号が入っている": [{"id": row.id, "題": row.title, "なろうの番号": row.narou_id}
                         for row in rows if row.narou_id in listed_ids],
        "番号がなろうの一覧に無い": [{"id": row.id, "題": row.title, "なろうの番号": row.narou_id}
                              for row in rows if row.narou_id is not None and row.narou_id not in listed_ids],
        "db に題の当たらないなろうの行": unmatched_listed,
        "なろうに題の当たらない db の行": [{"id": row.id, "題": row.title}
                                   for waiting in rows_by_title.values() for row in waiting],
    }


def match_novels(apply: bool, headed: bool) -> dict[str, list[dict]]:
    """なろうの小説の一覧を作品に当てはめる(作品の名前と小説の題で組む)。"""
    with get_env_session() as s:
        rows = [Row(id=story.id, title=story.name, narou_id=story.narou_novel_id)
                for story in s.scalars(select(Story).order_by(Story.id))]
    with open_site(headed) as site:
        novels = listed_links(site, NOVEL_LIST_URL, NOVEL_ID_PATTERN)
    result = pair_by_title(rows, novels)
    if apply:
        with get_env_session() as s, s.begin():
            for pair in result["当てはめる"]:
                UpdateStory(StoryUpdateForm(id=pair["id"], narou_novel_id=pair["なろうの番号"])).execute(s)
        logger.info("作品 %d 件に小説の番号を入れた", len(result["当てはめる"]))
    return result


def match_parts(story_id: int | None, apply: bool, headed: bool) -> dict[int, dict[str, list[dict]]]:
    """なろうの小説ごとに、部分の一覧を話に当てはめる(話の題とサブタイトルで組む)。

    `story_id` を渡せば、その作品の話を投稿する小説だけを見る。本文の無い話も見る(なろうに投稿してあり、db に本文の無い話がある)。
    """
    with get_env_session() as s:
        if story_id is None:
            novel_ids = sorted(set(s.scalars(select(Story.narou_novel_id).where(Story.narou_novel_id.is_not(None)))))
        else:
            novel_ids = [novel_id_of(s, story_id)]
        linked = {part.episode_id: part.novel_data_id for part in s.scalars(select(NarouPart))}
        rows = {novel_id: [Row(id=e.id, title=e.title, narou_id=linked.get(e.id))
                           for e in novel_episodes(s, novel_id)]
                for novel_id in novel_ids}
    with open_site(headed) as site:
        results = {novel_id: pair_by_title(rows[novel_id],
                                           listed_links(site, NOVEL_URL.format(novel=novel_id), PART_LINK_PATTERN))
                   for novel_id in novel_ids}
    if apply:
        with get_env_session() as s, s.begin():
            for result in results.values():
                # 当てはめた時点で、なろうの本文はその話と同じとみなす(投稿した時刻を今にする)
                for pair in result["当てはめる"]:
                    record_posted(s, pair["id"], pair["なろうの番号"])
        logger.info("話 %d 件に部分の番号を入れた", sum(len(result["当てはめる"]) for result in results.values()))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("login", help="ブラウザを開いて手でログインし、クッキーを残す")
    post = commands.add_parser("post", help="話を次話として投稿する(投稿した話なら、その部分を書き換える)")
    post.add_argument("--episode", type=int, required=True, help="話の id")
    post.add_argument("--submit", action="store_true", help="確認画面から投稿まで押す(無ければ確認画面で止める)")
    post.add_argument("--force", action="store_true", help="投稿のあとに直していない話(なろうが最新)も書き換える")
    post.add_argument("--headed", action="store_true", help="ブラウザを見える形で開く")
    commands.add_parser("outdated", help="投稿のあとに直した(なろうが古い)話を出す")
    link = commands.add_parser("link", help="話に部分の番号を手で結ぶ(結んだ時点で、なろうの本文はその話と同じとみなす)")
    link.add_argument("--episode", type=int, required=True, help="話の id")
    link.add_argument("--part", type=int, required=True, help="部分の番号(部分の管理画面の URL の noveldataid)")
    unlink = commands.add_parser("unlink", help="話と部分の結びを外す(なろうで部分を消したときなど)")
    unlink.add_argument("--episode", type=int, required=True, help="話の id")
    match_novels_command = commands.add_parser("match-novels", help="なろうの小説の一覧を作品に当てはめる")
    match_parts_command = commands.add_parser("match-parts", help="なろうの部分の一覧を話に当てはめる")
    match_parts_command.add_argument("--story", type=int, help="この作品の話を投稿する小説だけを見る(無ければ番号のある小説すべて)")
    for command in (match_novels_command, match_parts_command):
        command.add_argument("--apply", action="store_true", help="案のとおりに番号を書く(無ければ案を出すだけ)")
        command.add_argument("--headed", action="store_true", help="ブラウザを見える形で開く")
    args = parser.parse_args()

    configure_logging()
    ensure_local()
    if args.command == "login":
        login()
    elif args.command == "post":
        post_episode(args.episode, args.submit, args.force, args.headed)
    elif args.command == "outdated":
        print(json.dumps(outdated_episodes(), ensure_ascii=False, indent=2))
    elif args.command == "link":
        save_posted(args.episode, args.part)
        logger.info("話 %d に部分 %d を結んだ", args.episode, args.part)
    elif args.command == "unlink":
        unlink_part(args.episode)
        logger.info("話 %d と部分の結びを外した", args.episode)
    elif args.command == "match-novels":
        print(json.dumps(match_novels(args.apply, args.headed), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(match_parts(args.story, args.apply, args.headed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
