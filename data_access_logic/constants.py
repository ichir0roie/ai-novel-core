#!/usr/bin/env python3
from __future__ import annotations

# data_access_logic/character/generator
GENERATION_CHARACTER_AGE_RANGE = (0, 40)
# 話のプロットの役どころから生む人物(上役・老人など)は、時の流れの中で生む人物より年かさまで要る
SCENE_CHARACTER_AGE_RANGE = (0, 90)
# 中身を決めるときに説明ごと渡す「既にいる人物・対象」の上限。born_location とその祖先
# (国・大陸まで)全体の居住者を対象にするため、世界が育つほど際限なく
# 増える。上限が無いとプロンプトが肥大化し続ける(名付けで避ける名は、名前だけなので上限を置かない)。
NEARBY_CHARACTER_LIMIT = 20
# data_access_logic/character/naming
# AI に出させる名前の候補の数。この中からサイコロで選ぶ
NAME_CANDIDATE_COUNT = 10
# 人物の名の拍数。名付けのたびにこの幅からサイコロで一つ選んで AI に縛りとして渡す
NAME_MORA_RANGE = (3, 5)

NON_PERSON_KINDS = ("国", "組織", "商会", "氏族", "集団", "物")

# data_access_logic/character/generate_characters
# 場所の種別(location.kind)ごとに、その場所にじかにいる(配下の場所は数えない)人物・対象の上限。
# ランダムに人物を足す(GenerateCharacters)とき、上限に達した場所には足さない。話の役どころから作る人物は限らない。
# 世界が作者の手を離れて広がっても、一つの場所に名のある人物が溢れて扱いきれなくならないようにする
RESIDENT_LIMITS = {"都市": 40, "町": 30, "国": 30, "村": 20}
# RESIDENT_LIMITS に無い種別(森・洞窟・湖・大陸など)の上限
DEFAULT_RESIDENT_LIMIT = 10

# data_access_logic/event/progress・data_access_logic/character/cast
# 出来事を考えるとき、判断材料として渡す「直近の出来事」の件数(場所ごと・人物ごとの窓に使う)。
# 増やすほど過去の語彙が持ち越され、自己増殖しやすくなる一方、
# 少なすぎると同じ展開が場所・人物を変えて繰り返されているのを
# 見分ける材料が足りなくなる(「同じ出来事を名前だけ変えて繰り返さない」
# 2026-09 の観測)。どちらのリスクも残ったままの折衷値として置く。
RECENT_EVENT_LIMIT = 5

# data_access_logic/event/progress
# 移動先の候補(`character/moves.py` の `move_destinations`)をどこまで拾うか。read_cast の既定
# (levels=1、「隣の集落にいる者も枠に入れる」)と同じ考え方をそろえる。
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
# 文体の見本として本文を渡す、同じ作品(章・外伝を含む)の直前の話の本数。話の中身は、この話より前のすべての話の概要で渡す。
EPISODE_STYLE_SAMPLE_COUNT = 5
# 登場人物一人ぶんに渡す、直近の出来事の件数。
EPISODE_CHARACTER_EVENT_LIMIT = 3
# 話の場所で起きた直近の出来事を、いくつまで渡すか。
EPISODE_PLACE_EVENT_LIMIT = 3

# data_access_logic/idea
# 清書に渡すアイデアの上限(直接当たったものと、その上位・下位を合わせて)。
IDEA_CONTEXT_LIMIT = 100
# 清書に渡すアイデア一件の本文の字数の上限。
IDEA_CONTEXT_LETTERS = 400
