---
name: revise-episode
description: すでに本文のある話(episode)を、直す指示に沿って AI に書き直させる。指示の箇所だけでなく、指示と材料(作品・前の話・登場人物)を総合的に判断して本文を大幅に書き直してよい(大筋は保つ)。「エピソード5を推敲して」「初登場キャラの描写を厚くして」「この話の口調を直して」などの依頼で使う。
---

`CLAUDE.md` のルールに従う。入口は `episode.revise_episode.ReviseEpisode`(引数は下の「渡すもの」)。

## 回し方(場所で分ける)

回し方と、id・話の並びの引き方は場所で違う。環境変数 `CLAUDE_CODE_REMOTE` を見て、当たる方だけを Read する。

| `CLAUDE_CODE_REMOTE` | 読むファイル | 形 |
| --- | --- | --- |
| `true` でない(手元) | `.claude/skills/revise-episode/local.md` | db に直に繋ぎ、入口 `ReviseEpisode` を呼ぶ |
| `true`(web のセッション) | `.claude/skills/revise-episode/web.md` | db には繋がず、同じ処理を API 越しに回す(`web_session/`) |

## 渡すもの

- `episode`: `EpisodeForm(id=<episodeのid>)`。本文のある話だけ
- `instruction`(直す指示): 「初登場キャラの外見・性格を三人称で細かく書く」のように一言で渡す。空だと止まる
- `character_ids`: 対象の話に登場する人物を先に全員洗い出してから渡す(引き方は回し方のファイル)。人物ごとに調べ直しを繰り返さない。
  省けばその話の登場人物(`episode_character`)のまま。話題・回想・噂に名前が出るだけの人物は入れない(下の「入口がすること」)
- `model` / `effort`: 本文は `claude-opus-5-5` の `high` で書く。モデルを変えるよう頼まれたときだけ `model='claude-fable-5-1', effort='high'` のように渡す
- `shared_style_extra` / `style_extra`: この世界の舞台設定・既存の話から抽出した文体の癖(db の `style_preference` の `shared` / `episode` の行)は
  入口が自分で読む。別の値で書かせたいときだけ渡す

## 入口がすること

- 名前が出るだけの人物は、推敲の前後にプロット・本文から名前で拾い、`episode_character` に `mentioned=true` の行として登録し、
  その人物の設定(歳・口調・人物像)も AI に渡す
- 前の話の概要に出ていない人物は、自動で初登場と判断し、外見・性格の描写を厚くする
  (`style_preference` の `episode` の行に書いた「初めて出す人物は…」の方針に沿う)。Claude 側で初登場かどうかを判定し直さない
- 指示の箇所だけを字面どおりに直すのではなく、指示の意図と材料(作品・前の話・登場人物・場所)を総合的に判断して、
  場面の組み立て・順序・会話・描写の配分まで含めて本文を大幅に書き直してよい。話の大筋(誰が何をしてどうなるか)は保つ。
  大筋そのものを書き換えたいならスキル `episode` を使う
- 渡した指示は、話のプロット(`episode.plot_text`)の末尾の「## 推敲」の節に箇条書きで自動で積まれる(二回目以降も見出しは重ねない)。
  Claude 側で別途プロットへ書き込まない
- 書き直した本文から概要を作り直す
- 生物・医療・兵器の話題は、AI へ渡す文面の決まり(`ai/instructions/sensitive.py`)に沿って物語に要る抽象度にとどめる
- 中で `claude -p` を呼ぶので数分〜十数分かかる。Bash の `run_in_background` で回し、終わりの知らせを待つ(`sleep` で待たない)

## 報告する

終わったら、書き直した話を読み(読み方は回し方のファイル)、直った箇所を短く報告する。
本文が得られなければ `ValueError`(「本文が得られなかった」)で止まるので、そう伝える。

GUI からも同じ処理を呼べる(話の詳細画面の、本文のある話にだけ出る「AI で推敲する」ボタン。`gui/readme.md`)。
web の画面で押したものは待ち行列に積まれ、スキル `run-ai-tasks` で回る。
