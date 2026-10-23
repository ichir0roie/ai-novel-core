---
name: weekly-revision
description: 本文のある話を、直した時刻(`episode.updated_at`)の古い順に一話ずつ推敲し、その話のプロット・本文と、関わる行(人物・関係・スキル・場所・設定・出来事・本文の無い先の話のプロット)を整え、足りない行を足す。ユーザの指示も認めも待たずに回し、Claude の週の使用量(`seven_day` の使用率)が 95% に達したら止める。毎週木曜 18 時ごろに起きる予定のタスクが新しい web のセッションで呼ぶ。「定期推敲」「週の推敲を回して」などの依頼でも使う。
---

予定のタスクから新しい web のセッションで起きる。見ている人はいないので、ユーザに尋ねず、認めも待たずに最後まで回す。

- 回すのは web のセッション(`CLAUDE_CODE_REMOTE=true`)。db は `.claude/docs/web-db.md` の API 越しに読み書きする
- `CLAUDE.md` の「実装からプルリクまで」は当てない。コードは変えず、コミット・push・PR はしない(リポジトリに変えたものを残さない)
- 作品の大筋(誰が何をしてどうなるか)は変えない。変えないと解けない食い違いは直さずに報告に挙げる
- 行は消さない(話・人物・場所・設定・出来事・関係)。人物・関係・場所の来歴の今の行は書き換えず、足す。直してよいのは、推敲する話の時刻に足してある来歴の行(スキル `revise-episode` の 6)と、下の 3 で挙げた行だけ
- 推敲する話のほかで本文のある話は、本文・プロットに触らない(直すと `updated_at` が新しくなり、その話の番が後ろへ回る)。食い違いは報告に挙げ、その話の番に直す

## 使用量を読む

止めどころは、このセッションの記録に出る使用率で決める。

1. `mcp__claude-code-remote__get_session` を `session_id` を省いて呼び、このセッションの id(`ccr.id`)を得る(始めに一度)
2. `mcp__claude-code-remote__list_events` に `session_id`・`kinds: ["rate_limit_event"]`・`limit: 100` を渡し、返った `data` の最後(一番新しい)の `rate_limit_event.internal_anthropic_catchall.rate_limit_info` を読む。`data` が空なら `before_id` に `first_id` を渡してさかのぼる
   - `unifiedWindows.seven_day.utilization`: 週の使用率(0〜1)。`resetsAt` は週の区切り(UNIX 秒)
   - `unifiedWindows.five_hour.utilization`・`resetsAt`: 5 時間ごとの使用率と区切り
   - `isUsingOverage`: 上限を越えて追加の料金で回っているか
3. 読めなかったら(見出しが無い・使用率が無い)、推敲を始めずに止め、読めなかったことを報告する(当て推量で回し続けない)

## 流れ

始めに、スクラッチパッドに `weekly-revision/progress.md` を作り、始めの使用率(`seven_day` の `utilization` と `resetsAt`)を書く。一話を終えるたびに、話の id・題・終えたときの週の使用率を一行足す。会話が要約されても、ここから続きを読む。

1. **止めるか決める**: 「使用量を読む」で使用率を読み、次のどれかに当たれば下の「終える」へ
   - `seven_day.utilization` が 0.95 以上
   - `seven_day.utilization` に、直前の一話で増えた分(二話目から。`progress.md` の差)を足すと 0.95 を越える
   - `seven_day.resetsAt` が始めに書いた値と違う(週が明けた。次の週の分は使わない)
   - `isUsingOverage` が true
   - 下の 2 で推敲する話が残っていない

   止めないときでも、`five_hour.utilization` が 0.9 以上なら、5 時間の上限で途中に止まらないよう休む。`mcp__claude-code-remote__send_later` で `five_hour.resetsAt` の 2 分後に「weekly-revision を続ける」と `progress.md` の中身を送り、返答を終える(休むあいだにコンテナが片付けられるとスクラッチパッドも消えるので、中身を送り返しに持たせる)。届いたら、`progress.md` が無ければ送り返しの中身から作り直し、1 から続ける
2. **話を選ぶ**: 本文のある話を、`updated_at` の古い順に引き、このセッションでまだ推敲していない先頭の一話を取る

   ```
   api="${NOVEL_API_URL%/}"; h="x-novel-api-key: $NOVEL_API_KEY"
   curl -sS -H "$h" "$api/api/tables/episode/records?sort=updated_at&order=asc&limit=500" -o <scratchpad>/weekly-revision/queue.json
   jq -c '[.items[] | select(.letters > 0) | {id, title, letters}][:5]' <scratchpad>/weekly-revision/queue.json
   ```

   - 500 件で本文のある話が尽きたら `offset` を足して次を引く
   - 推敲を終えた話は `updated_at` が新しくなって後ろへ回る。毎週この順で回すと、前の週の続きから始まる
3. **推敲する**: 選んだ話を、スキル `revise-episode` の流れ 1〜6 で直す。ただし直す指示はユーザから受けず、自分で決める
   - 材料: `ReadEpisodeBrief` に加え、前後の話(`ReadEpisodes` の並びで前後一話ずつ。前は本文、後は本文が無ければプロット)・登場人物ごとの時刻を渡さない `ReadCharacter`・関係(`ListCharacterRelations`)・場所(表の API の `location`)・出来事(`ReadEvents` の `character_id` / `location_id`)を読む
   - 直す指示を決める: 次の観点で、この話と関わる行の食い違い・足りない所を挙げ、それを直す指示を自分で書く(スキル `story-director` の 2 の 4「矛盾を確かめる」の観点も使う)
     - 本文と、この話の書き方(材料の「書き方」)・プロット・前後の話・人物の芯と来歴・関係・場所・設定との食い違い
     - 初登場の人物の外見・性格の描写、場面の運び、会話と描写の配分の薄い所
     - 本文に出るのに db に無い人物・場所・語、話に結んでいない登場人物・場所
   - 本文とプロット: `revise-episode` の 2〜5 で書き直して `ReviseEpisode` で確定する。プロットの「## 推敲」の節には `- 定期推敲 <年/月/日(日本時間の今日)>: <決めた指示の要点>` を一行足す。プロットが本文と食い違っていれば、プロットの本体も本文に合わせて書き直す
   - 関わる行: 確定のあと、`revise-episode` の 6 と、スキル `episode` の手順 10 で人物の来歴・装い・スキルを整える。関係・場所・設定・出来事の食い違いと足りない行は、スキル `story-director` の「入口」の表と 3 の 2 の行ごとの決まりで直す・足す(提案して認めを待つ所は飛ばす)。どの行も、書く前にその文の範囲の書き方を `ReadWritingStyle` で読む
   - 先の話: この話の後にある本文の無い話のプロットが、直した本文・行と食い違えば、`story-director` の「話の行を書く」でそのプロットを直す。本文のある話は直さず報告に挙げる
   - 一話の推敲が途中で失敗したら(入口のエラーなど)、その話は直せた所までにして、何が残ったかを `progress.md` に書き、次の話へ進む
4. `progress.md` に一行足して 1 へ戻る

## 終える

`progress.md` から次をまとめて、このセッションの最後の返答にする(本文・プロット・材料のような長いものは貼らない)。

- 止めた理由と、始めと終わりの週の使用率
- 推敲した話ごとに: 話の id・題・字数の変わり方・決めた指示の要点・直した・足した行(表ごとに)
- 直さずに残した食い違い(大筋に触れるもの・本文のある別の話のもの)と、途中で失敗した話
