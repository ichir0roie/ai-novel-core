# テスト

テストは一度すべて消した。テストをしてと明確に依頼されたら、そのとき要るテストを `tests/` に書いて実行する。

- テストは `novel.test.db` だけを読み書きする(書くときは `tests/conftest.py` で `tool.test` を先に読んで固定する)。本番の `novel.db` には書き込まない
- `novel.test.db` は空から作らず、本番の `novel.db` を写して作る(`tool.test.copy_novel_db`。`seed_mock_db --recreate`
  もこれを使う)。手で動きを確かめるときも、これで写した `novel.test.db` を使う
- AI を呼ぶ処理では本物の claude を呼ばない。`tool.test.mock_ai_client.MockAIClient` を `ai` に渡すか、
  `ai.claude_code.ai_client.generate` を差し替える
- alembicのテスト、ダウングレードのテストはやらない。
