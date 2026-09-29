# ユーザーの好みを反映するインストラクション

`core`(このリポジトリ)はどの世界でも使い回す汎用の仕組みなので、世界の舞台設定・既存の話から
抽出した文体の癖のような、世界(ユーザー)ごとに違う「好み」は `core` に定数として持たない。

- `core` 側には、システム固有の値(どの世界でも成り立つ既定値。ラノベとしての基本文体など)だけを
  `ai/instructions/` の定数として置く
- ユーザーが追加する値(舞台設定・抽出した文体の癖など)は親リポジトリ(世界リポジトリ)側に
  `core/` と同階層の python モジュール(例: `instructions/style.py`)として置く
- 親リポジトリ側の値は、AI へ渡す文面を組み立てる末端の生成関数(`ai/instructions/style.py` の
  `style_instruction()`、`data_access_logic/episode/` の `write_episode`、`data_access_logic/event/novelist.py` の `novelize_event` など、
  入口の `GenerateEpisode` / `ReviseEpisode` / `GenerateEvent` など)の引数として渡す。
  `core` は「引数を渡さなければ空でよい(システム固有の値だけで成り立つ)」設計にする

例: `ai/instructions/style.py` の `shared_extra` / `extra`、`main.py` 以下の `shared_style_extra` /
`style_extra`。呼び出し元(世界リポジトリの `instructions/` や、Claude Code のスキル)がこれらの引数に
自分の値を渡す。
