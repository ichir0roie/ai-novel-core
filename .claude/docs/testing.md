# テスト

テストをしてと明確に依頼されたら、テストの実装と網羅テストを実行する。

- `tests/` に pytest のテストがある。
- テストは `novel.test.db` だけを読み書きする(`tests/conftest.py` が`tool.test` を先に読んで固定する)。本番の `novel.db` には触れない
- alembicのテスト、ダウングレードのテストはやらない。
