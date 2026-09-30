---
name: episode
description: 話のプロット(`plot_text`)・時刻・登場人物・前の話・作品を決めて、作品に話(episode)を一話ぶん書いて足す。プロット・時刻だけ決めた話(本文の無い episode)に本文だけを書くのにも使う。「このプロットで話を書いて」「〇〇と△△が出る話を 11579/03/02 で」「エピソードを作って」「この枠の本文を書いて」などの依頼で使う。
---

`CLAUDE.md` のルールに従う。リポジトリのルートの `.venv` の python で次を回す(db は SessionStart フックが渡す `DEM_DATABASE_URL`)。

```
.venv/bin/python -c "
from data_access_logic.episode.form import EpisodeForm
from data_access_logic.episode.generate_episode import GenerateEpisode
episode = GenerateEpisode(EpisodeForm(
    story_id=<作品id>, plot_text='''<話のプロット>''', start='<年/月/日>', character_ids=[<人物id>, ...],
    location_id=None, viewpoint_character_id=None)).run()
print('EPISODE_ID', episode['id'])
"
```

プロット・時刻の入った話(本文の無い episode)に本文だけを書くときは、`EpisodeForm` に `id` だけを渡す
(プロット・時刻・視点・場所・題はその話のものを使う)。人物を変えるときは `EpisodeForm` の `character_ids` に渡す(省けばその話の登場人物)。

```
episode = GenerateEpisode(EpisodeForm(id=<episodeのid>, character_ids=[<人物id>, ...])).run()
```

- この世界の舞台設定・既存の話から抽出した文体の癖(db の `style_preference` の `shared` / `episode` の行)は、
  入口が自分で読む。渡さなくてよい(別の値で書かせたいときだけ `shared_style_extra` / `style_extra` に渡す)
- 作品 id・人物 id・場所 id は db の `story` / `character` / `location` から引く(名前で頼まれたら `select id, name from ... where name like ...`)。
  時刻は `'11579/03/02'` のように書く
- プロットは `data_access_logic/readme.md` の「補足」にある `## 場面` / `## 狙い` の形に割ってから渡すとよい。
  プロットに無い出来事は足されない
- 話に渡す登場人物は、話と人物のリレーション(`episode_character`)だけ。渡した `[<人物id>, ...]` はその話の `episode_character` として残る。
  枠へ書くときに `character_ids` を省けば、枠の `episode_character` を使う。時刻・場所から人物を拾う既定は無い
- 名前が出るだけの人物(話題・回想・噂)は `character_ids` に入れない。プロット・本文に名前が出る承認済みの人物は、
  話の保存・枠の生成・プロット補完・推敲のたびに `episode_character` の `mentioned=true` の行として拾い直され、
  その設定(歳・口調・人物像)も「名前だけ出る人物」として AI に渡る
- 前の話は、作品の中でその時刻より前の話が自動で渡る(直前の五話は本文、それより前は概要。名指しはできない)。
  章・外伝のように親の作品(`story.parent_story_id`)の子になっている作品では、一番上の作品とその子孫の話をまとめて時刻の順に見る
- プロット(`plot_text`)か時刻(`start`)が空なら、先に AI が枠(題・プロット・時刻)を決めてから本文を書く。プロットと時刻は渡しておく
- 題・時刻だけ決めた本文の無い話(episode)があれば、`EpisodeForm` の `id` にその id を渡してそこへ書く(新しい話を足さない)。
  プロット・時刻・視点・場所は省けばその話のものを使い、題は残る。作品に同じ時刻の話が無いかを先に `episode` から引いて確かめる
- 場所・視点を決めるなら `location_id` / `viewpoint_character_id`(どちらも id。人物・場所の名前は AI に自由記述させず、db から引いた id をそのまま渡す)。場所を省くと作品の立つ場所を材料にし、視点を省くと NULL のまま残る(AI には選ばせない)
- 話は一つの `episode` テーブルにプロット(`plot_text`)と本文(`main_text`)、本文の概要(`summary_text`)をまとめて持つ(GUI では話のページの `main_text`)
- 本文は `claude-opus-5-5` の `high` で書き、それ以外(要約・アイデアの引き当てなど)は `claude-opus-5-5` の `low`。
  本文のモデルを変えるよう頼まれたら `GenerateEpisode(..., model='claude-fable-5-1', effort='high')` のように渡す(db には残らない)
- 中で `claude -p` を数回呼び、本文は一話ぶん書くので十数分かかる。タイムアウトは長め(20 分)に取る
- 生物・医療・兵器の話題は、AI へ渡す文面の決まり(`ai/instructions/sensitive.py`)に沿って物語に要る抽象度にとどめる
- 終わったら `EPISODE_ID` の話を db から読み、題・時刻・視点・字数(`episode.letters`)・あらすじを短く報告する。
  `[data_access_logic/idea] 候補を足した:` の行があれば、足したアイデアの候補も添える。本文が得られなければ `ValueError`(「本文が得られなかった」)で止まるので、そう伝える(枠は保存したまま残る)

すでに本文のある話を、書き直す・書き足す(推敲する)ときはスキル `revise-episode` を使う。
