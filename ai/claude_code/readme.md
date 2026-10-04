# claude_code

生成を Claude Code(`claude -p`)にやらせるための client と、検証の処理。
生成そのもの(人物・出来事・話)は `data_access_logic/` の入口(`GenerateCharacter` / `GenerateEvent` / `GenerateFrame` など)にあり、
AI を `ai` 引数(`data_access_logic/ai_client.py` の `AIClient`)で受け取る。既定はここの `ai_client`。

```
ai/claude_code/
  ai_client.py            `generate(prompt, 出力のモデル, ...)`。出力のモデルの json schema を渡して
                          `claude -p --output-format json --json-schema …` を subprocess で呼び、そのモデルで返す(得られなければ None)
  fact_checker.py         oracle・ミームを Dラボのナレッジとネット検索で検め、妥当性と補足を `fact_check` 欄へ書く
```

## 仕組み

- 各呼び出しは `--tools ""`(道具なし。`tools=("WebSearch", "WebFetch")` を渡したときだけ、その道具を許す)・`--no-session-persistence`・`--system-prompt`
  で、単発の「プロンプト → JSON」に絞る。カレントは一時ディレクトリにして、
  このリポジトリの `CLAUDE.md` や設定を読み込ませない
- モデルと effort は `ai_client.py` の `_MODEL`(`claude-opus-5-5`)・`_EFFORT`(`low`)を既定にし、`--model` `--effort` に渡す
- 認証は CLI に任せる(`claude login` 済みか `ANTHROPIC_API_KEY`)

## 環境変数(`.env` でよい)

| 変数                    | 意味                                                                                                 |
| ----------------------- | ---------------------------------------------------------------------------------------------------- |
| `DEM_CLAUDE_AI_COMMAND` | 実行する CLI。既定 `claude`                                                                          |
| `DEM_CLAUDE_AI_TIMEOUT` | 一回の呼び出しを待つ秒数の下限。既定 600(CLI の起動と思考のぶん、呼び出し側の timeout では足りないことがある) |
| `DEM_CLAUDE_AI_DLAB_TOOLS` | 検める(`fact_checker.py`)ときに許す Dラボの道具。カンマ区切りの許可ルール、既定 `mcp__d-lab`。`claude mcp list` の Dラボのサーバー名に合わせて `mcp__<サーバー名>` にする。空にすると Dラボを使わない |
| `DEM_CLAUDE_AI_MCP_CONFIG` | MCP の道具を使わせる呼び出しで `--mcp-config` に渡すファイル。Dラボを claude.ai のコネクタ以外で繋ぐときに使う。既定なし |
