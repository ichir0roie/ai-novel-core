# テスト

テストをしてと明確に依頼されたら、そのとき要るテストを `tests/` に書いて実行する(`.venv/bin/python -m pytest tests`)。

- テストは手元の PostGIS のテスト用の db(`novel_test`。開発用の db と同じサーバー)だけを読み書きする。書くときは
  `tests/conftest.py` で `tool.test` を先に読んで固定する。本番の RDS には書き込まない(`tool.test` は、テスト用の db が
  手元のサーバーを指していなければ止まる)。`DEM_DEV_DATABASE_URL` が無ければ、`tool.test` がその場で `infra_local/postgis.sh` を回して用意する
- テスト用の db は空から作らず、本番の RDS を写して作る(`tool.test.copy_production_db`)。写し元は手元の転送越しの RDS なので、
  転送(`tool.aws.rds --serve`)が要る。手で動きを確かめるときも、これで写した db を使う
- `conftest.py` はテストの始めに `tool.test.ensure_test_db` を回す。テスト用の db が無いか空のときだけ写し、行があればそのまま使う
  (前のテストで足した行も残る)。作り直すのは `.venv/bin/python -m tool.test.recreate_db`(VS Code はタスク「test db recreate」。
  `seed_mock_db --recreate` も写し直す)。マイグレーションを足したあと、版の食い違いの警告が出たときも作り直す
- AI を呼ぶ処理では本物の claude を呼ばない。`tool.test.mock_ai_client.MockAIClient` を `ai` に渡すか、
  `ai.claude_code.ai_client.generate` を差し替える
- alembicのテスト、ダウングレードのテストはやらない。
