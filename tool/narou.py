#!/usr/bin/env python3
"""話の本文を、Playwright で小説家になろうへ投稿する。手元だけで動かす(web のセッションでは止まる)。

ログインは最初に一度だけ人が手で行い、そのときのクッキー(Playwright の storage state)を
`.cache/narou/storage_state.json` に残す。以後の投稿はそれを読んでログイン済みとして動く。
クッキーが切れていたら `login` からやり直す。

    .venv/bin/python -m tool.narou login                          # ブラウザが開くので、手でログインする
    .venv/bin/python -m tool.narou post --episode 61 --novel 123  # 次話投稿の確認画面まで進め、スクショを撮って止まる
    .venv/bin/python -m tool.narou post --episode 61 --novel 123 --submit  # 確認画面から投稿まで押す

`--novel` は、なろうの小説管理の画面の URL に出る小説の番号(Nコードではない)。
初めて動かす手元では、ブラウザを `.venv/bin/python -m playwright install chromium` で入れておく。

仮実装: なろうの画面の URL・入力欄・ボタンは確かめていない(下の定数)。初めて投稿するときに画面と突き合わせて直す。
"""
from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from data_access_logic.logs import configure_logging
from db.schema import Episode, get_env_session

logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "narou"
STATE_FILE = STATE_DIR / "storage_state.json"

LOGIN_URL = "https://ssl.syosetu.com/login/input/"
USER_TOP_URL = "https://syosetu.com/user/top/"
NEW_PART_URL = "https://syosetu.com/usernovelmanage/ziwainput/ncode/{novel}/"
SUBTITLE_FIELD = "input[name='subtitle']"
TEXT_FIELD = "textarea[name='novel']"
CONFIRM_BUTTON = "input[type='submit'][value*='確認']"
SUBMIT_BUTTON = "input[type='submit'][value*='投稿']"

# 手でログインし終えるのを待つ長さ
LOGIN_TIMEOUT_MS = 10 * 60 * 1000


@dataclass
class Post:
    episode_id: int
    subtitle: str
    text: str


def ensure_local() -> None:
    # web のセッションのコンテナにはクッキーを置かず、本番の作品をそこから外へ出さない
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        raise SystemExit("なろうへの投稿は手元だけで動かす。web のセッションでは動かさない")


def is_login_page(url: str) -> bool:
    return "/login/" in url


def read_post(episode_id: int) -> Post:
    with get_env_session() as s:
        episode = s.get(Episode, episode_id)
        if episode is None:
            raise SystemExit(f"話 {episode_id} が無い")
        if not episode.main_text.strip():
            raise SystemExit(f"話 {episode_id} に本文が無い")
        if not (episode.title or "").strip():
            raise SystemExit(f"話 {episode_id} に題(サブタイトル)が無い")
        return Post(episode_id=episode.id, subtitle=episode.title, text=episode.main_text)


def login() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL)
        logger.info("ブラウザでなろうにログインする(%d 分待つ)", LOGIN_TIMEOUT_MS // 60000)
        page.wait_for_url(lambda url: not is_login_page(url), timeout=LOGIN_TIMEOUT_MS)
        context.storage_state(path=STATE_FILE)
        browser.close()
    if os.name == "posix":
        STATE_FILE.chmod(0o600)
    logger.info("ログインのクッキーを %s に残した", STATE_FILE)


def fill_new_part(page: Page, novel: int, post: Post) -> None:
    """次話投稿の画面を開いてサブタイトルと本文を入れ、確認画面まで進める。"""
    page.goto(NEW_PART_URL.format(novel=novel))
    if is_login_page(page.url):
        raise SystemExit("ログインが切れている。`python -m tool.narou login` でやり直す")
    page.fill(SUBTITLE_FIELD, post.subtitle)
    page.fill(TEXT_FIELD, post.text)
    page.click(CONFIRM_BUTTON)
    page.wait_for_load_state()


def post_episode(episode_id: int, novel: int, submit: bool, headed: bool) -> None:
    if not STATE_FILE.exists():
        raise SystemExit("ログインのクッキーが無い。先に `python -m tool.narou login` で手でログインする")
    post = read_post(episode_id)
    screenshot = STATE_DIR / f"episode-{episode_id}-confirm.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(storage_state=STATE_FILE)
        page = context.new_page()
        fill_new_part(page, novel, post)
        page.screenshot(path=screenshot, full_page=True)
        logger.info("確認画面のスクショ: %s", screenshot)
        if submit:
            page.click(SUBMIT_BUTTON)
            page.wait_for_load_state()
            logger.info("話 %d を投稿した: %s", episode_id, page.url)
        else:
            logger.info("確認画面で止めた(投稿するなら --submit を付けて回し直す)")
        # 入れ替わったクッキーを残し、次の投稿でもログインを保つ
        context.storage_state(path=STATE_FILE)
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("login", help="ブラウザを開いて手でログインし、クッキーを残す")
    post = commands.add_parser("post", help="話を次話として投稿する")
    post.add_argument("--episode", type=int, required=True, help="話の id")
    post.add_argument("--novel", type=int, required=True, help="なろうの小説管理の画面の小説の番号")
    post.add_argument("--submit", action="store_true", help="確認画面から投稿まで押す(無ければ確認画面で止める)")
    post.add_argument("--headed", action="store_true", help="ブラウザを見える形で開く")
    args = parser.parse_args()

    configure_logging()
    ensure_local()
    if args.command == "login":
        login()
    else:
        post_episode(args.episode, args.novel, args.submit, args.headed)


if __name__ == "__main__":
    main()
