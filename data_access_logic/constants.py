#!/usr/bin/env python3
from __future__ import annotations

# data_access_logic/character/generator
GENERATION_CHARACTER_AGE_RANGE = (0, 40)
# 命名時の重複回避に渡す「既にいる人物・対象」の上限。born_location とその祖先
# (国・大陸まで)全体の居住者を対象にするため、世界が育つほど際限なく
# 増える。上限が無いとプロンプトが肥大化し続ける。
NEARBY_CHARACTER_LIMIT = 20

NON_PERSON_KINDS = ("国", "組織", "商会", "氏族", "集団", "物")

# data_access_logic/event/progress
# 移動先候補(_move_destinations)をどこまで拾うか。read_cast の既定
# (levels=1、「隣の集落にいる者も枠に入れる」)と同じ考え方をそろえる。
REACH_LEVELS = 1
MOVE_DESTINATION_LIMIT = 20
# 当事者一人ぶんに渡す相関の上限。
RELATION_LIMIT = 10
# 出来事を起こす時点より後に既にある出来事を、いくつまで渡すか。
LATER_EVENT_LIMIT = 5
# event_duration_days の取りうる範囲。範囲外の値は丸める。
EVENT_DURATION_RANGE_DAYS = (1, 90)
DEFAULT_EVENT_DURATION_DAYS = 1
# サイコロで選ぶ候補の件数。少ないと交渉型の無難な候補だけで埋まり、
# 多いと本文を書く段で候補の要約が薄くなる。
CANDIDATE_COUNT = 6

# data_access_logic/event/summary
# 直前の出来事の本文を要約させるのを待つ秒数。
EVENT_SUMMARY_TIMEOUT = 120.0

# data_access_logic/event_seed
# 出来事の種を抜き出すとき、一度の呼び出しで渡す元の本文の字数の上限。
EVENT_SEED_BATCH_LETTERS = 6000
EVENT_SEED_TIMEOUT = 300.0
# 出来事の生成(`GenerateEvent`)で、一件の出来事に引く種の件数。候補はこの種か、直前の出来事からの連想で立てる。
EVENT_SEED_DRAW_COUNT = 3
# 棚卸し前の種がこの件数たまったら、似た種をまとめる。
EVENT_SEED_CONSOLIDATE_EVERY = 50
# 棚卸しで一度に見比べる、棚卸し済みの種の字数の上限(棚卸し前の種は毎回すべて添える)。
EVENT_SEED_CONSOLIDATE_LETTERS = 15000

# data_access_logic/meme
# ミームを抜き出すとき、一度の呼び出しで渡す元の本文の字数の上限。
MEME_BATCH_LETTERS = 6000
MEME_TIMEOUT = 300.0
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
# 本文を一話ぶん書かせるので、断片の JSON より長く待つ秒数。
EPISODE_TIMEOUT = 900.0
# キー情報補完で、種を書き直させるのを待つ秒数。
EPISODE_KEY_TIMEOUT = 300.0
# 書き直した種から、材料に無い人物・舞台の候補を抜き出させるのを待つ秒数。
EPISODE_CASTING_TIMEOUT = 300.0
# 前の話を名指ししないときに、作品の中から渡す直前の話の本数。
EPISODE_PREVIOUS_LIMIT = 3
# 登場人物一人ぶんに渡す、直近の出来事の件数。
EPISODE_CHARACTER_EVENT_LIMIT = 3
# 話の場所で起きた直近の出来事を、いくつまで渡すか。
EPISODE_PLACE_EVENT_LIMIT = 3

# data_access_logic/episode/summary
# 話一話ぶんの概要・文体を覚え書きにさせるのを待つ秒数。
RECAP_TIMEOUT = 300.0

# data_access_logic/idea
IDEA_TERMS_TIMEOUT = 300.0
# 清書に渡すアイデアの上限(直接当たったものと、その上位・下位を合わせて)。
IDEA_CONTEXT_LIMIT = 100
# 清書に渡すアイデア一件の本文の字数の上限。
IDEA_CONTEXT_LETTERS = 400
IDEA_POLISH_TIMEOUT = 300.0
