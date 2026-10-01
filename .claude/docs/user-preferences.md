# ユーザーの好みを反映するインストラクション

`core`(このリポジトリ)はどの世界でも使い回す汎用の仕組みなので、世界の舞台設定・既存の話から
抽出した文体の癖のような、世界(ユーザー)ごとに違う「好み」は `core` に定数として持たない。

- `core` 側には、システム固有の値(どの世界でも成り立つ既定値。ラノベとしての基本文体など)だけを
  `ai/instructions/` の定数として置く
- ユーザーが追加する値(舞台設定・抽出した文体の癖など)は db の `style_preference` 表に、効く対象(`target`)ごとに一行で持つ。
  `shared` はどの対象にも効き、`episode` などはその対象だけに効く。GUI の「文体の好み」の一覧か、
  入口 `style_preference.commit_style_preference.CommitStylePreference` / `update_style_preference.UpdateStylePreference` で足す・直す
- 好みの値は、AI へ渡す文面を組み立てる末端の生成関数(`ai/instructions/style.py` の
  `style_instruction()`、`data_access_logic/episode/` の `write_episode` など)には引数として渡す。
  `core` は「引数を渡さなければ空でよい(システム固有の値だけで成り立つ)」設計にする

入口の `GenerateEpisode` / `ReviseEpisode` は、`shared_style_extra` / `style_extra` を省かれると
`style_preference` から読む(`data_access_logic/style_preference/extras.py`。web のセッションは段 `style_preference.steps.style_extras` 越し)。
行が無ければ空のまま動く。明示して渡した値(空文字を含む)は db の値より優先する。
このセッションの Claude が自分で本文を書く・直すとき(スキル `episode` / `revise-episode`)は、`ReadEpisodeBrief` の材料の
「書き方」に、システム固有の文体と `style_preference` の `shared` / `episode` の行を合わせた文面が入る(`data_access_logic/episode/brief.py`)。
