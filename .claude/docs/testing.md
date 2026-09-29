# テスト

テストをしてと明確に依頼されたら、テストの実装と網羅テストを実行する。

- `tests/` に pytest のテストがある。
- テストは `novel.test.db` だけを読み書きする(`tests/conftest.py` が`tool.test` を先に読んで固定する)。本番の `novel.db` には書き込まない
- `novel.test.db` は空から作らず、本番の `novel.db` を写して作る(`tool.test.copy_novel_db`。conftest・`seed_mock_db --recreate`
  はどちらもこれを使う)。手で動きを確かめるときも、これで写した `novel.test.db` を使う
- alembicのテスト、ダウングレードのテストはやらない。
