---
name: revise-episode
description: すでに本文のある話(episode)を、直す指示に沿って AI に書き直させる。指示の箇所だけでなく、指示と材料(作品・前の話・登場人物)を総合的に判断して本文を大幅に書き直してよい(大筋は保つ)。「エピソード5を推敲して」「初登場キャラの描写を厚くして」「この話の口調を直して」などの依頼で使う。
---

`CLAUDE.md` のルールに従う。リポジトリのルートの `.venv` の python で次を回す(db は SessionStart フックが渡す `DEM_DATABASE_URL`)。

```
.venv/bin/python -c "
from data_access_logic.episode.form import EpisodeForm
from data_access_logic.episode.revise_episode import ReviseEpisode
episode = ReviseEpisode(EpisodeForm(id=<episodeのid>), '''<直す指示>''', character_ids=[<人物id>, ...],
    model=None, effort=None).run()
print('EPISODE_ID', episode['id'])
"
```

- 対象の話に登場する人物(`character_ids`)は先に全員洗い出してから渡す。人物ごとに調べ直しを繰り返さない
  - 話題・回想・噂に名前が出るだけの人物は `character_ids` に入れない。`ReviseEpisode` が推敲の前後にプロット・本文から
    名前で拾い、`episode_character` に `mentioned=true` の行として登録し、その人物の設定(歳・口調・人物像)も AI に渡す
  - その作品の話の並びは `episode.read_episodes.ReadEpisodes(story_id, count=..., text=False)` で一度に取る
    (`start` 順で返るので、並びを確かめる select を別に打ち直さない)
  - 対象の話の本文に出る名前から人物 id を引く(`select id, name from character where name like '%<名>%'`)
  - 前の話の概要に出ていない人物は、`ReviseEpisode` が自動で初登場と判断し、外見・性格の描写を厚くする
    (`style_preference` の `episode` の行に書いた「初めて出す人物は…」の方針に沿う)。
    Claude 側で初登場かどうかを別途判定し直す必要は無い
- `instruction`(直す指示)は「初登場キャラの外見・性格を三人称で細かく書く」のように一言で渡す。
  空だと止まる
- 指示の箇所だけを字面どおりに直すのではなく、指示の意図と材料(作品・前の話・登場人物・場所)を総合的に判断して、
  場面の組み立て・順序・会話・描写の配分まで含めて本文を大幅に書き直してよい。話の大筋(誰が何をしてどうなるか)は保つ。
  大筋そのものを書き換えたいならスキル `episode` を使う
- 渡した `instruction`(直す指示)は、話のプロット(`episode.plot_text`)の末尾に「## 推敲」の節として自動で積まれる。
  二回目以降も見出しは重ねず、既にある節に箇条書きを足していく。何を直したかの履歴として残るので、
  Claude 側で別途プロットへ書き込む必要は無い
- この世界の舞台設定・既存の話から抽出した文体の癖(db の `style_preference` の `shared` / `episode` の行)は、
  入口が自分で読む。渡さなくてよい(別の値で書かせたいときだけ `shared_style_extra` / `style_extra` に渡す)
- 本文は `claude-opus-5-5` の `high` で書く。モデルを変えるよう頼まれたら `model='claude-fable-5-1', effort='high'` のように渡す
- 中で `claude -p` を呼ぶので数分かかる。タイムアウトは長め(20 分)に取る
- 生物・医療・兵器の話題は、AI へ渡す文面の決まり(`ai/instructions/sensitive.py`)に沿って物語に要る抽象度にとどめる
- 終わったら `EPISODE_ID` の話を db から読み、直った箇所を短く報告する。本文が得られなければ `ValueError`(「本文が得られなかった」)で止まるので、そう伝える

GUI からも同じ処理を呼べる(話の詳細画面の、本文のある話にだけ出る「AI で推敲する」ボタン。`gui/readme.md`)。
