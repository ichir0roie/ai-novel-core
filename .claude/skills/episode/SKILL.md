---
name: episode
description: 話のプロット(`plot_text`)・時刻・登場人物・前の話・作品を決めて、作品に話(episode)を一話ぶん書いて足す。プロット・時刻だけ決めた話(本文の無い episode)に本文だけを書くのにも使う。「このプロットで話を書いて」「〇〇と△△が出る話を 11579/03/02 で」「エピソードを作って」「この枠の本文を書いて」などの依頼で使う。
---

`CLAUDE.md` のルールに従う。入口は `episode.generate_episode.GenerateEpisode`(引数は下の「渡すもの」)。

## 回し方(場所で分ける)

回し方と、id・話の引き方は場所で違う。環境変数 `CLAUDE_CODE_REMOTE` を見て、当たる方だけを Read する。

| `CLAUDE_CODE_REMOTE` | 読むファイル | 形 |
| --- | --- | --- |
| `true` でない(手元) | `.claude/skills/episode/local.md` | db に直に繋ぎ、入口 `GenerateEpisode` を呼ぶ |
| `true`(web のセッション) | `.claude/skills/episode/web.md` | db には繋がず、同じ処理を API 越しに回す(`web_session/`) |

## 渡すもの

`GenerateEpisode(EpisodeForm(...))` の `EpisodeForm` に渡す。

- 新しい話: `story_id`(作品 id)・`plot_text`(プロット)・`start`(時刻。`'11579/03/02'` のように書く)・`character_ids`(人物 id のリスト)。
  場所・視点を決めるなら `location_id` / `viewpoint_character_id`
- 本文の無い話(プロット・時刻だけ、または題・時刻だけ決めた枠)へ書く: `id` だけを渡す(新しい話を足さない)。
  プロット・時刻・視点・場所・題はその話のものを使う。人物を変えるときだけ `character_ids` を渡す(省けば枠の `episode_character`)
- 新しい話を足す前に、作品に同じ時刻の話が無いかを引いて確かめる(引き方は回し方のファイル)
- 作品・人物・場所は名前で頼まれても、引いた id をそのまま渡す(AI に名前を自由記述させない)
- プロットは `data_access_logic/readme.md` の「補足」にある `## 場面` / `## 狙い` の形に割ってから渡すとよい。
  プロットに無い出来事は足されない
- この世界の舞台設定・既存の話から抽出した文体の癖(db の `style_preference` の `shared` / `episode` の行)は、
  入口が自分で読む。渡さなくてよい(別の値で書かせたいときだけ `shared_style_extra` / `style_extra` に渡す)
- 本文は `claude-opus-5-5` の `high` で書き、それ以外(要約・アイデアの引き当てなど)は `claude-opus-5-5` の `low`。
  本文のモデルを変えるよう頼まれたら `model='claude-fable-5-1', effort='high'` のように渡す(db には残らない)

## 入口がすること

- 話に渡す登場人物は、話と人物のリレーション(`episode_character`)だけ。渡した `character_ids` はその話の `episode_character` として残る
- 本文を書く前に、AI がプロットで台詞・行動のある人物を挙げて登場人物に足す(渡した人物は外さない)。
  db の人物と呼び名が違っても照合し、db にいない人物は自動生成で作って足す。なので `character_ids` は、
  必ず出したい人物(視点など)だけ渡せばよい。作られた人物は報告に含める
- 名前が出るだけの人物(話題・回想・噂)は `character_ids` に入れない。プロット・本文に名前が出る承認済みの人物は、
  話の保存・枠の生成・プロット補完・推敲のたびに `episode_character` の `mentioned=true` の行として拾い直され、
  その設定(歳・口調・人物像)も「名前だけ出る人物」として AI に渡る
- 前の話は、作品の中でその時刻より前の話が自動で渡る(直前の五話は本文、それより前は概要。名指しはできない)。
  章・外伝のように親の作品(`story.parent_story_id`)の子になっている作品では、一番上の作品とその子孫の話をまとめて時刻の順に見る
- プロット(`plot_text`)か時刻(`start`)が空なら、先に AI が枠(題・プロット・時刻)を決めてから本文を書く。プロットと時刻は渡しておく
- 場所を省くと作品の立つ場所を材料にし、視点を省くと NULL のまま残る(AI には選ばせない)
- 話は一つの `episode` テーブルにプロット(`plot_text`)と本文(`main_text`)、本文の概要(`summary_text`)をまとめて持つ(GUI では話のページの `main_text`)
- 生物・医療・兵器の話題は、AI へ渡す文面の決まり(`ai/instructions/sensitive.py`)に沿って物語に要る抽象度にとどめる
- 中で `claude -p` を数回呼び、本文は一話ぶん書くので十数分かかる。Bash の `run_in_background` で回し、終わりの知らせを待つ(`sleep` で待たない)

## 報告する

終わったら書いた話を読み(読み方は回し方のファイル)、題・時刻・視点・字数(`episode.letters`)・あらすじを短く報告する。
出力に `[data_access_logic/idea] 候補を足した:` の行があれば、足したアイデアの候補も添える。
本文が得られなければ `ValueError`(「本文が得られなかった」)で止まるので、そう伝える(枠は保存したまま残る)。

すでに本文のある話を、書き直す・書き足す(推敲する)ときはスキル `revise-episode` を使う。
