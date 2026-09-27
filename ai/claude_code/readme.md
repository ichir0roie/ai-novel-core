# claude_code

`ai/local_ai/`(Ollama)と**同じ仕様**で、生成を Claude Code(`claude -p`)にやらせる側。
常駐ループの本体(生成器・時刻・定数)は上位の `ai/time_keeper/` にあり、local_ai と
claude_code はそこへ自分の `ai_client` を渡すだけの薄い入口になっている。

```
ai/time_keeper/          常駐ループの本体(両方で共用)。生成器は AI を `ai` 引数(`_ai.AIClient`)で受け取る
ai/claude_code/
  ai_client.py            `ai/local_ai/ai_client.py` と同じ関数(generate / generate_json / try_generate_json)。
                          中身は `claude -p --output-format json --json-schema …` の subprocess
  claude_code_time_keeper.py  `ai/time_keeper/main.py` に claude_code の ai_client を渡して回す入口
  story_writer.py         作品の次の話を書いて db へ確定する(local_ai に無い、ここだけの生成器)
  fact_checker.py         アイデア・oracle・ミームを Dラボのナレッジとネット検索で検め、妥当性と補足を `fact_check` 欄へ書く(local_ai に無い)
  interface/              Claude が db を読み書きする入口(一覧は interface/readme.md)
```

## 仕組み

- 各呼び出しは `--tools ""`(道具なし。`tools=("WebSearch", "WebFetch")` を渡したときだけ、その道具を許す)・`--no-session-persistence`・`--system-prompt`
  で、単発の「プロンプト → JSON」に絞る。カレントは一時ディレクトリにして、
  このリポジトリの `CLAUDE.md` や設定を読み込ませない
- モデルと effort は `ai_client.py` の `_MODEL`(`claude-sonnet-5`)・`_EFFORT`(`medium`)を既定にし、`--model` `--effort` に渡す。
  話の本文(`episode`)の生成(`story_writer.py`・`claude_plot_main`・`claude_episode_main`)だけは
  `EPISODE_MODEL`(`claude-fable-5-1`)・`EPISODE_EFFORT`(`high`)を渡す
- 認証は CLI に任せる(`claude login` 済みか `ANTHROPIC_API_KEY`)
- ループの終わりに Claude Code の呼び出し回数・トークン・費用を出す

## 環境変数(`.env` でよい)

| 変数                    | 意味                                                                                                 |
| ----------------------- | ---------------------------------------------------------------------------------------------------- |
| `DEM_CLAUDE_AI_COMMAND` | 実行する CLI。既定 `claude`                                                                          |
| `DEM_CLAUDE_AI_TIMEOUT` | 一回の呼び出しを待つ秒数の下限。既定 600(CLI の起動ぶん、Ollama 向けの 120 秒では足りないことがある) |
| `DEM_CLAUDE_AI_DLAB_TOOLS` | 検める(`fact_checker.py`)ときに許す Dラボの道具。カンマ区切りの許可ルール、既定 `mcp__d-lab`。`claude mcp list` の Dラボのサーバー名に合わせて `mcp__<サーバー名>` にする。空にすると Dラボを使わない |
| `DEM_CLAUDE_AI_MCP_CONFIG` | MCP の道具を使わせる呼び出しで `--mcp-config` に渡すファイル。Dラボを claude.ai のコネクタ以外で繋ぐときに使う。既定なし |

## 使い方

常駐ループ(local_ai と同じ引数):

```
.venv/bin/python -c "
from ai.claude_code.claude_code_time_keeper import claude_main
claude_main(year=2027, max_days=30)
"
```

`year` を省くと db の最新の時刻から続ける。プロット(`Plot`)が一件も掛かって
いない時刻に来たら止まるのも local_ai と同じ。

毎日のルーチン(サブキャラクター一人の次の出来事を一件起こす):

```
.venv/bin/python -c "
from ai.claude_code.interface.sync.sync_db import SyncDb
from ai.claude_code.claude_code_time_keeper import claude_daily_event_main
SyncDb().run()
claude_daily_event_main()
SyncDb().run()
"
```

- `claude_daily_event_main(character_id)` と渡すと、その人物を主役にする(新しく足した人物の最初の出来事を起こすときなど)。
  その時刻に対象にならなければ None を返す
- 生きているサブキャラクターからランダムに一人選び、その者の最新の出来事(終わりが一番新しいもの)の
  終わりから 1〜7 日後(`constants.NEXT_EVENT_GAP_DAYS`)を始まりにする。出来事がまだ無ければ、
  居場所に一番近く掛かる作品の `start`(生まれより後なら生まれ)から数える
- その時刻に居場所が無い者・`active_random_generation` でない場所に居る者は選び直す
  (常駐ループが出来事の対象にしない者は、ここでも対象にしない)
- 直前の出来事は、本文の代わりに要約(`event_summary.py`)を渡す。要約は `event_summary` テーブル
  (md には出さない)に残し、本文が変わっていなければ作り直さない。要約が作れなければ本文のまま渡す
- 組み立ては常駐ループの `event_progression_generator` と同じ(当事者ごとの推測 → 候補をサイコロ → 記録)。
  選んだ者は必ず当事者に入る。居合わせる者のうち、自分の時間が既に先へ進んでいる者は加えない
- 記録として起こしたあと、本文(`text`)だけを話と同じ小説の形、一話の三分の一(`EVENT_NOVEL_TARGET_LETTERS`)に
  書き直す(`ai/instructions/event_writing.py` の `EVENT_NOVEL_INSTRUCTION`)。書けなければ記録のまま残す

本文を書く(作品 `story_id` の次の話を 1 話。`episodes_to_write` で続けて書く):

```
.venv/bin/python -c "
from ai.claude_code.story_writer import write_story
write_story(story_id=1, episodes_to_write=1)
write_story(story_id=1, plot_id=40)     # 種だけ入っている話(id=40)を埋める
"
```

材料は `start_story` 入口と同じ(作品の見出し・直前の話・断面・顔ぶれ)。
直前の話は 3 話(`RECAP_EPISODE_LIMIT`)まで、本文の代わりに概要で渡す。書く前に一話ずつ本文を読ませて
概要と文体の覚え書きを作らせ、概要を直前の話として、一番新しい話の文体の覚え書きと一緒に本文のプロンプトへ載せる。
覚え書きは `story_summary` テーブル(md には出さない)に一話ずつ残し、本文が変わっていなければ作り直さない。
概要が作れなかった話は本文のまま渡す。

- 書く話は `plot_id` で指す。省くと**本文の入っている最後の話の次**(`start` の順)を書く。
  その位置に種だけの話が無ければ、`start` の無い新しい話として末尾に足す。
  種(`key`)だけ入れてある先の話は「まだ書かれていない」扱いなので、
  先まで種を並べてある作品でも止まらない
- その話に種があればプロンプトへ載せ、視点・場所・種はそのままに、題と本文だけを上書きする
- 止めるのは、**その話より前に**「本文はあるのに `synced` が下りている話」がある場合だけ
- 書いた話は `synced=True` で確定する。本文は話の `episode` に入れる
- 本文の長さ・場面の切り方・文体は `ai/instructions/style.py`
  (`EPISODE_TARGET_LETTERS` / `EPISODE_STYLE_BASE`)
