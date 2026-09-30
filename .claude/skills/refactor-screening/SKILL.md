---
name: refactor-screening
description: core リポジトリ全体を定期的にスクリーニングし、処理の共通化・シンプルな実装・余計な機能が無いかを確認してリファクタリングする。実装がモックに合わせて不自然に分岐していないかも見る。見つけて直したら core に PR を作る(直接 main へは入れない)。「リファクタのスクリーニング」「定期リファクタ」「コードの健全性チェック」「core を整理して」などの依頼で使う。
---

`CLAUDE.md` のルールに従う。対象はこのリポジトリ全体(`ai/` `db/` `gui/` `data_access_logic/` など)。
db の行(RDS)は変更しない。

手順は手元(`CLAUDE_CODE_REMOTE` が `true` でない)向けに書いてある。web のセッション(`CLAUDE_CODE_REMOTE=true`)では次のように読み替える。

- 1 の worktree は切らない。セッションが指定したブランチで、リポジトリのルートのまま作業する(5 の worktree の後始末も要らない)
- 4 の本番を写したテスト用の db は作れない(RDS に繋がない)。`tool.test.mock_ai_client` とコードを読むことで確かめ、
  写した db で確かめていないことを PR と報告に書く
- 5 の PR は `gh` ではなく GitHub の MCP のツールで作る

## 1. 作業場所を用意する

このスキルを呼ばれたことを、worktree・コミット・push・PR の作成の依頼とみなす。今のブランチを乱さないよう worktree を切る。

```
git worktree add ../core-refactor -b refactor/screening-<YYYYMMDD>
```

以降、コードの読み書きは `../core-refactor/` に対して行う。python はこのリポジトリの `.venv` の python を使い、
`../core-refactor` を cwd に、`PYTHONPATH` にも `../core-refactor` を渡して動かす(`.claude/docs/setup.md` 参照)。

## 2. スクリーニングする

`../core-refactor/` の全体を、前回(claude interface と gui の共通化)と同じ 3 つの観点で読む。
特定のディレクトリに絞らず、`ai/` `db/` `gui/` `data_access_logic/` を一通り見る。

- **処理の共通化**: 同じ形の定型処理(id を取り出す・存在確認する・setattr して確定する、
  session を開いて閉じる、AI を呼んで結果を整形する、など)が複数ファイルに複製されていないか。
  すでにある共通の基底・ヘルパーを使わず書かれていないか
- **シンプルな実装**: 使われていない引数・分岐・クラス、過剰な抽象化(1 箇所でしか使わない
  ヘルパー、汎用化しすぎて逆に追いにくくなった層)、死んでいるコード(参照されていない関数・
  ファイル、廃止済みのはずの仕組みの残骸)がないか
- **余計な機能**: 依頼にも仕様にも無い機能(先回りして足した設定項目・フラグ・将来のための
  拡張ポイント)が、使われないまま残っていないか

見つけた項目はメモしておき、次に進む前に「直す価値があるか(効果 > 手間、かつ壊れにくいか)」
を選別する。db のスキーマや入口(`data_access_logic/<領域>/`)の入出力仕様(gui や web のセッションが読む
`inspect.signature`・エラーの型など)を変える修正は、呼び出し側への影響を必ず確認する。

## 3. テストの扱い

- テストは一度すべて消してある。テストを書いて回すのは、ユーザーに頼まれたときだけ
  (`.claude/docs/testing.md`)
- 実装がモックに合わせて不自然に分岐していないかは見る(モックの都合で残っている使われない引数など)
- データベースのマイグレーション(alembic のリビジョン)にはテストを書かない。`schema.py` を変えたときだけ
  `alembic check` を手で打って確かめる

## 4. 直して確かめる

- 見つけた項目のうち選別したものを直す。一度に大きく変えすぎず、レビューできる粒度に留める
- 直す前後で、`tool.test.copy_production_db` で本番を写したテスト用の db と `tool.test.mock_ai_client` を使い、
  直した入口の結果・AI に渡すプロンプトが変わっていないかを確かめる
- 直す前後で、`gui/api/interface.py` が `inspect.signature` で読む入口の引数構成や、
  `UnknownRecordError`/`ValueError` のような呼び出し側が見る例外の型を変えていないか確認する
  (変える場合は gui 側・呼び出し元も一緒に直す)

## 5. 送る

- **直す項目が無かった場合**は PR を作らず、worktree を消してその旨を報告して終わる
  (`git worktree remove ../core-refactor`)
- **直した場合**は worktree 内でコミットし、そのブランチを push して **PR を作る**。
  merge はしない(PR の merge はユーザが決める)。このリポジトリは公開なので、push の前に `.claude/docs/aws.md` の
  「core は公開リポジトリ」の grep で、構築の値が紛れていないか確かめる

```
git -C ../core-refactor push -u origin refactor/screening-<YYYYMMDD>
gh pr create --head refactor/screening-<YYYYMMDD> --title "<短い要約>" --body "<見つけた項目・直した内容・テストの結果>"
```

- 終わったら worktree を消す(`git worktree remove ../core-refactor`)
- 見つけた項目・直した項目・見送った項目・テスト結果・PR の URL(作った場合)を短く報告する
