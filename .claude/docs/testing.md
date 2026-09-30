# テスト

テストをしてと明確に依頼されたら、そのとき要るテストを `tests/` に書いて実行する(`.venv/bin/python -m pytest tests`)。

- テストは手元の PostGIS のテスト用の db(`novel_test`。開発用の db と同じサーバー)だけを読み書きする。書くときは
  `tests/conftest.py` で `tool.test` を先に読んで固定する。本番の RDS には書き込まない(`tool.test` は、テスト用の db が
  手元のサーバーを指していなければ止まる)
- テスト用の db は空から作らず、本番の RDS を写して作る(`tool.test.copy_production_db`。`conftest.py` がテストの始めに回し、
  `seed_mock_db --recreate` もこれを使う)。写し元は手元の転送越しの RDS なので、転送(`tool.aws.rds --serve`)が要る。
  手で動きを確かめるときも、これで写した db を使う
- AI を呼ぶ処理では本物の claude を呼ばない。`tool.test.mock_ai_client.MockAIClient` を `ai` に渡すか、
  `ai.claude_code.ai_client.generate` を差し替える
- alembicのテスト、ダウングレードのテストはやらない。
