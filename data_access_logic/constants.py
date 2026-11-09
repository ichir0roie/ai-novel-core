#!/usr/bin/env python3
from __future__ import annotations

# data_access_logic/character/generator
GENERATION_CHARACTER_AGE_RANGE = (0, 40)
# 話のプロットの役どころから生む人物(上役・老人など)は、時の流れの中で生む人物より年かさまで要る
SCENE_CHARACTER_AGE_RANGE = (0, 90)
# 中身を決めるときに説明ごと渡す「既にいる人物・対象」の上限。born_location の祖先(国・大陸まで)の居住者が対象で、
# 世界が育つほど増えてプロンプトが肥大化するため(名付けで避ける名は名前だけなので上限を置かない)。
NEARBY_CHARACTER_LIMIT = 20
# data_access_logic/character/naming
# AI に出させる名前の候補の数。この中からサイコロで選ぶ
NAME_CANDIDATE_COUNT = 10
# 人物の名の元にする意味の語を AI に挙げさせる数。この中からサイコロで `NAME_MEANING_PICK_RANGE` 個選ぶ
NAME_MEANING_COUNT = 10
NAME_MEANING_PICK_RANGE = (1, 2)

NON_PERSON_KINDS = ("国", "組織", "商会", "氏族", "集団", "物")

# data_access_logic/character/generate_characters
# 場所の種別(location.kind)ごとの、その場所にじかにいる(配下は数えない)人物・対象の上限。
# ランダムに人物を足す(GenerateCharacters)ときだけ効き、話の役どころから作る人物は限らない。
RESIDENT_LIMITS = {"都市": 40, "町": 30, "国": 30, "村": 20}
# RESIDENT_LIMITS に無い種別(森・洞窟・湖・大陸など)の上限
DEFAULT_RESIDENT_LIMIT = 10

# data_access_logic/event/progress・data_access_logic/character/cast
# 出来事を考えるときに渡す直近の出来事の件数(場所ごと・人物ごと)。多いと過去の語彙が持ち越されて自己増殖し、
# 少ないと名前だけ変えた同じ展開の繰り返しを見分けられない。その折衷値。
RECENT_EVENT_LIMIT = 5

# data_access_logic/event/progress
# 移動先の候補(`character/moves.py` の `move_destinations`)を何段上の場所の配下から拾うか。read_cast の既定(levels=1)にそろえる。
REACH_LEVELS = 1
MOVE_DESTINATION_LIMIT = 20
# 出来事を起こす時点より後に既にある出来事を、いくつまで渡すか。
LATER_EVENT_LIMIT = 5
# event_duration_days の取りうる範囲。範囲外の値は丸める。
EVENT_DURATION_RANGE_DAYS = (1, 90)
DEFAULT_EVENT_DURATION_DAYS = 1
# サイコロで選ぶ候補の件数。少ないと交渉型の無難な候補だけで埋まり、
# 多いと本文を書く段で候補の要約が薄くなる。
CANDIDATE_COUNT = 6

# data_access_logic/event_seed
# 出来事の種を抜き出すとき、一度の呼び出しで渡す元の本文の字数の上限。
EVENT_SEED_BATCH_LETTERS = 6000
# 出来事の生成(`GenerateEvent`)で、一件の出来事に引く種の件数。候補はこの種か、直前の出来事からの連想で立てる。
EVENT_SEED_DRAW_COUNT = 3
# 棚卸し前の種がこの件数たまったら、似た種をまとめる。
EVENT_SEED_CONSOLIDATE_EVERY = 50
# 棚卸しで一度に見比べる、棚卸し済みの種の字数の上限(棚卸し前の種は毎回すべて添える)。
EVENT_SEED_CONSOLIDATE_LETTERS = 15000

# data_access_logic/meme
# ミームを抜き出すとき、一度の呼び出しで渡す元の本文の字数の上限。
MEME_BATCH_LETTERS = 6000
# 抜き出したミームの重複を見るとき、一度に見比べる既存のミームの字数の上限(新しいミームは毎回すべて添える)。
MEME_DEDUPE_LETTERS = 15000
# 人物・対象を生むときに、分類ごとに引くミームの件数の幅。
MEME_DRAW_RANGE = (0, 2)
# 人物・人物以外の対象に引く分類。「理」は世界の法則で、誰かが持つ考え方ではないので引かない。
MEME_PERSON_CATEGORIES = ("信条", "欲求", "境遇")
MEME_NON_PERSON_CATEGORIES = ("信条", "欲求", "集団")
# 引いたミームごとにランダムに一つ割り振る、その人物の中での置き場所。
MEME_POSITIONS = {
    "古": "かつて持っていたが、今は手放した",
    "今": "いま持っている",
    "表": "人前で掲げている",
    "裏": "内に秘めている",
}

# data_access_logic/episode
# 登場人物の話し方を調整する根拠にする、同じ作品(章・外伝を含む)の直前の話の本数。
EPISODE_VOICE_SAMPLE_COUNT = 5
# 文体の見本として渡す、同じ作品(章・外伝を含む)の直前の話の本文の字数の上限。新しい話から、まるごと収まるだけ渡す。
EPISODE_STYLE_SAMPLE_LETTERS = 12000
# 登場人物を決める前に、人物一人ぶん読む関わった話(この話の直前から)の本数。それより前のことは人物の来歴から読む。
EPISODE_RECENT_APPEARANCE_COUNT = 5
# 登場人物一人ぶんに渡す、直近の出来事の件数。
EPISODE_CHARACTER_EVENT_LIMIT = 3
# 本文の材料に、登場人物一人ぶんの来歴の出来事の行(種別の無い行)を、新しいほうからいくつまで渡すか。
# 持ち物など種別の付いた行は、その時刻に効いているものをすべて渡す
EPISODE_BRIEF_HISTORY_LIMIT = 5
# 話の場所で起きた直近の出来事を、いくつまで渡すか。
EPISODE_PLACE_EVENT_LIMIT = 3

# data_access_logic/idea
# 清書に渡すアイデアの上限(直接当たったものと、その上位を合わせて)。
IDEA_CONTEXT_LIMIT = 100
# 清書に渡すアイデア一件の本文の字数の上限。
IDEA_CONTEXT_LETTERS = 400

# data_access_logic/expansion(人物モード `ActCharacter`)
# 動く人物を渡さないとき、その時刻の行動力ごとの重みでサブキャラクターから引く。無は動かない
ACTOR_WEIGHTS = {"無": 0, "低": 1, "並": 2, "高": 3, "必": 5}
# 人物が前に出た出来事・話から、次の一手までに空ける日数の範囲
ACT_INTERVAL_DAYS = (1, 30)
# 人物が見る、居合わせる人物の上限
ACT_PRESENT_LIMIT = 10
# 狙いの成り行き。サイコロで一つ選び、裁く段に渡す(狙いがいつも通るとは限らない)
ACT_OUTCOMES = ("思い通りに運ぶ", "半ばだけ運ぶ", "思わぬ方へ転ぶ", "裏目に出る")
# 一手で生む人物・アイデアの上限(影響の枠がさらに絞る)
ACT_NEW_CHARACTER_LIMIT = 2
ACT_NEW_IDEA_LIMIT = 3
# 人物の目の段(狙い・対話の手番)は数が多いので一番安いモデルで回し、裁く段だけを強いモデルで実行ごとに一回にまとめる
ACT_MODEL = "claude-haiku-5-5"
ACT_EFFORT = "low"
ACT_JUDGE_MODEL = "claude-opus-5-5"
ACT_JUDGE_EFFORT = "high"
# 一回の実行で回す手の上限(裁く段に一度に渡す数)
ACT_RUN_LIMIT = 8
# 語り部。一手の時刻の前後この日数に、動く人物か居合わせる人物が出る(プロットに名前が出る)プロットつきの話があれば、
# 近い話から上限まで、そのプロットを語り部の動機にする。語り部は一手ごとに一度だけ呼ぶ
ACT_NARRATOR_EPISODE_DAYS = 30
ACT_NARRATOR_EPISODE_LIMIT = 3
ACT_NARRATOR_MODEL = "claude-opus-5-5"
ACT_NARRATOR_EFFORT = "high"
# 段(無/低/並/高/必)の並び。影響力・行動力を数で比べるのに使う
LEVEL_RANKS = {"無": 0, "低": 1, "並": 2, "高": 3, "必": 4}
# 主要人物は、影響力の値が低くてもこの段より下に扱わない(ほかの人物の一手から動かされにくくする)
MAIN_CHARACTER_MIN_INFLUENCE = "高"
# 気力。行動力の段ごとの上限。一手を打つ・出来事の当事者になると減り、日が経つと戻る
ACT_ENERGY_MAX = {"無": 0, "低": 3, "並": 4, "高": 6, "必": 8}
# 気力が 1 戻るまでの日数(ゲームの中の日)
ACT_ENERGY_RECOVERY_DAYS = 7
# 気力の減り。自分から一手を打つ・ほかの人物の一手に巻きこまれるか当事者になる
ACT_COST_ACT = 2
ACT_COST_INVOLVED = 1
# 手数。この日数のあいだに一人が自分から打てる手の数
ACT_WINDOW_DAYS = 30
ACT_WINDOW_LIMIT = 3
# 巻きこみ。一手で巻きこめる相手の数と、対話の手番(動いた人物の最初の一手を除く)の上限
ACT_INVITE_LIMIT = 2
ACT_DIALOGUE_TURN_LIMIT = 6
# 影響の枠。動いた人物の影響力の段ごとに、来歴・居場所を動かせる人数、居場所を移せる人数、生める人物・アイデアの数
ACT_IMPACT_PEOPLE = {"無": 1, "低": 2, "並": 3, "高": 5, "必": 8}
ACT_IMPACT_MOVES = {"無": 1, "低": 1, "並": 2, "高": 3, "必": 5}
ACT_IMPACT_NEW_CHARACTERS = {"無": 0, "低": 1, "並": 1, "高": 2, "必": 2}
ACT_IMPACT_IDEAS = {"無": 1, "低": 1, "並": 2, "高": 3, "必": 3}
# 場所をなくす・作ることのできる、動いた人物の影響力の下限
ACT_IMPACT_LOCATION_MIN = "高"
# 成り行きが裏目・思わぬ方へ転んだときは、枠を一段狭める
ACT_NARROWING_OUTCOMES = ("思わぬ方へ転ぶ", "裏目に出る")

# data_access_logic/character/knowledge.py(人物役が読む、自分が言ったセリフ)
# 言ってからこの日数までは原文、ここから鮮明の日数までは鮮明、それより後はあやふやを渡す
SPEECH_VERBATIM_DAYS = 3
SPEECH_VIVID_DAYS = 365
