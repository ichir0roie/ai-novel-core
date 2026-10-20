---
name: run-ai-tasks
description: GUI で足した・直した行に後回しになっている AI の段(ミームの分類・アンチミームの作成・古い要約の作り直し)を、このセッションでまとめて回して報告する。行を指定されたら、その行からミーム・出来事の種も抜き出す。「作業やって」「溜まった AI の作業を回して」「後回しの AI を片付けて」「この話からミームを抜いて」などの依頼で使う。
---

GUI の追加・修正は確定だけして AI の段を回さないので、その分をここで回す(`.docs/claude-tasks.md` の「後回しの段」)。

| 回すもの | 入口 | 引数 |
| --- | --- | --- |
| ミームの分類・アンチミーム・古い要約(いつも) | `meme.refresh_generated_content.RefreshGeneratedContent` | `{}` |
| ミームの抜き出し(行を指定されたときだけ) | `meme.extract_memes.ExtractMemes` | `{"rows": [{"table": "<oracle / event / episode>", "id": …}, …]}` |
| 出来事の種の抜き出し(行を指定されたときだけ) | `event_seed.extract_event_seeds.ExtractEventSeeds` | `{"rows": [{"table": "<episode / character / event>", "id": …}, …]}` |

- ミーム・出来事の種は、抜き出し済みかの印を持たないので、溜まった行を自分で探して回さない。ユーザが指定した行(「ep79 から」「この人物の筋書きから」など)だけを渡す

## 1. 回す

- 手元: `.claude/docs/db.md` の「入口を呼ぶ」の形で、入口の id と引数を渡して回す
- web のセッション: 先に `.venv/bin/python -m web_session.check_api` を回す。終了コードが 0 でなければ、出力をそのまま報告して終わる(直さない。見るところは `.docs/web-session.md` の「確かめる」の表)。届けば `.claude/docs/web-db.md` の「呼び方」の形で、入口の id と引数を渡して流れを回す
- 数分〜十数分かかるので、Bash の `run_in_background` で回して終わりの知らせを待つ。途中で `sleep` で待たない

## 2. 報告する

最後に出た JSON(作り直した要約・足したミーム・種などの件数)を短く報告する。

## 守ること

- コード・データ・設定を直さない。git の commit・push をしない
- `NOVEL_API_KEY` の値・関数 URL を報告やログに書かない
