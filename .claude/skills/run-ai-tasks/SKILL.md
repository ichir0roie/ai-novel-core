---
name: run-ai-tasks
description: GUI で足した・直した行に後回しになっている AI の段(ミームの抜き出し・アンチミームの作成・古い要約の作り直し)を、このセッションでまとめて回して報告する。「作業やって」「溜まった AI の作業を回して」「後回しの AI を片付けて」などの依頼で使う。
---

`CLAUDE.md` のルールに従う。GUI の追加・修正は確定だけして AI の段を回さないので、その分をここで回す(`.docs/claude-tasks.md` の「後回しの段」)。
回すのは入口 `meme.refresh_generated_content.RefreshGeneratedContent`(引数なし)。

## 1. 回す

- 手元: `.claude/docs/db.md` の「入口を呼ぶ」の形で、入口の id と `{}` を渡して回す
- web のセッション: 先に `.venv/bin/python -m web_session.check_api` を回す。終了コードが 0 でなければ、出力をそのまま報告して終わる(直さない。見るところは `.docs/web-session.md` の「確かめる」の表)。届けば `.claude/docs/web-db.md` の「呼び方」の形で、入口の id と `{}` を渡して流れを回す
- 数分〜十数分かかるので、Bash の `run_in_background` で回して終わりの知らせを待つ。途中で `sleep` で待たない

## 2. 報告する

最後に出た JSON(作り直した要約・抜き出したミームなどの件数)を短く報告する。

## 守ること

- コード・データ・設定を直さない。git の commit・push をしない
- `NOVEL_API_KEY` の値・関数 URL を報告やログに書かない
