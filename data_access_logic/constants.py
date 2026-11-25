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

# data_access_logic/expansion(人物モード `SimulateDay`)
# 人物が最後に出た時刻が、世界の今(本文のある最新の話)からこの日数より前なら、世界の今から数える
ACT_STALE_DAYS = 90
# 一時間ごとの手の種別。人物の目が一つ選ぶ。眠る・食べる・触れ合うは、欲の規則(`expansion/needs.py`)に効く
DAY_ACTION_KINDS = ("眠る", "食べる", "触れ合う", "働く", "用事", "話す", "休む", "移動", "そのほか")
# 作者の出来事・話の予定で埋める時間。終わりの無い予定はこの時間だけ、終わりのある予定もこの時間までで切る(暦の一時間で数える)
DAY_FIXED_DEFAULT_HOURS = 2
DAY_FIXED_MAX_HOURS = 6
# 予定の中身として人物の目と記録に渡す、話のプロット・出来事の本文の字数
DAY_FIXED_LABEL_LETTERS = 300
# 欲の段(食欲・睡眠欲・性欲)ごとの強さ。食欲・性欲は一時間の増え方に、睡眠欲は眠りの長さに掛ける
DAY_NEED_RATES = {"無": 0.0, "低": 0.6, "並": 1.0, "高": 1.4, "必": 1.8}
DAY_SLEEP_RATES = {"無": 0.5, "低": 0.8, "並": 1.0, "高": 1.15, "必": 1.3}
# 睡眠欲の段ごとの、眠りの不足を取り戻す割合。低いほど、足りなくても起きやすい
DAY_SLEEP_RECOVERY = {"無": 0.0, "低": 0.3, "並": 0.6, "高": 0.9, "必": 1.0}
# 欲の段を決めていない人物の、年齢ごとの段(食欲・睡眠欲・性欲)。年齢がこの数より小さければ、その段
DAY_NEED_BY_AGE = ((6, ("並", "必", "無")), (13, ("高", "高", "無")), (18, ("高", "高", "低")), (40, ("並", "並", "並")),
                   (60, ("並", "並", "低")), (10000, ("低", "低", "低")))
# 年齢の分からない人物の段
DAY_NEED_UNKNOWN_AGE = ("並", "並", "低")
# 起きる・寝る時刻の基準。一日を 24 に割った刻みで書き、一日の長さが違う暦でも同じ割合にする。並の睡眠欲なら、24 時に寝て 8 時に起きる
DAY_BASE_WAKE = 8
DAY_BASE_SLEEP_HOURS = 8
# 眠りの不足を一晩で取り戻す時間の上限(一日を 24 に割った刻み)。取り戻す時間は、朝を遅らせる分と夜を早める分に半分ずつ分ける
DAY_SLEEP_RECOVERY_MAX = 4
# 寝る時刻のこの時間前より後に、人物が自分から眠ったら、その夜は床に就いたとして、朝まで会話に聞かずに寝床(住まい)で眠る
DAY_EARLY_BED_HOURS = 3
# 夜の始まり(一日を 24 に割った刻み)。これより後に人物が自分から眠っても、その夜は床に就いたとする(早寝のあと、眠り続けるかを毎時間聞かない)
DAY_NIGHT_START = 19
# 強いモチベーション(この強さ以上)があるとき・行動量に余裕がある(七日の和が上限のこの割合より下)とき、それぞれ一時間早く起き、一時間遅く寝る
DAY_EAGER_STRENGTH = 4
DAY_SPARE_LOAD_RATIO = 0.4
# 空腹と、人と触れ合いたい欲(0〜100)の一時間の増え方(一日 24 時間の暦での量。欲の段の強さと、前の日の不足の強さを掛ける)
DAY_HUNGER_PER_HOUR = 10
# 一時間に食べた量。種別が「食べる」でない一時間でも(話しながら料理をつまむなど)、食べた量で空腹を戻す
DAY_MEAL_AMOUNTS = ("なし", "少し", "しっかり")
# 「少し」食べたときに空腹が減る量(「しっかり」と、種別「食べる」は 0 に戻す)
DAY_SNACK_RELIEF = 40
# 一日を記録する段に渡す、動いた人物の前の出来事の名前の数(同じ名前の記録を続けて立てないように)
ACT_RECENT_EVENT_NAMES = 5
DAY_DESIRE_PER_HOUR = 3
# 人と話した一時間で、人と触れ合いたい欲が減る量(触れ合うと 0 に戻る)
DAY_TALK_DESIRE_RELIEF = 30
# 眠っているあいだの空腹の増え方(起きているときの割合)
DAY_SLEEP_HUNGER_SHARE = 0.25
# 前の日の不足(100 − 満ち足り方)を、次の日の欲の強さに足す割合
DAY_PRESSURE_GAIN = 1.0
# 欲がこの値を超えた時間を、満ち足りていない時間として数える
DAY_NEED_COMFORT = 50
# 不足をさかのぼって数える日数。行動量もこの日数の和で数える
DAY_LOOKBACK_DAYS = 7
# さかのぼった不足の和(日ごとの 100 − 満ち足り方の和)が、この値以上なら、その強さで欲を満たしたいモチベーションを持つ。最初の値より下なら持たない
DAY_NEED_MOTIVATION_STEPS = ((120, 2), (220, 3), (350, 4), (500, 5))
# 欲を満たしたいモチベーションの内容(食欲・睡眠欲・性欲)。同じ内容の効いている行を、強さの変わり目で終えて足し直す
DAY_NEED_MOTIVATIONS = {"food": "おなかいっぱい食べたい", "sleep": "ゆっくり眠りたい", "touch": "親しい人と触れ合いたい"}
# 行動量。一時間の重みは、その一時間にした行いのうち一番重いもの
DAY_DEED_WEIGHTS = {"外に出た": 1, "戦った": 2, "働いた": 3, "何かを傷つけた": 4, "ほかの人物を変えた": 5}
# 人物の会話に渡す、行いの意味
DAY_DEED_NOTES = {
    "外に出た": "住まいの外で過ごした", "戦った": "人や獣と力ずくでぶつかった", "働いた": "仕事・家の用・稼ぎのための作業をした",
    "何かを傷つけた": "人・獣・物を傷つけた・壊した",
    "ほかの人物を変えた": "相手の考え・立場・暮らしを変えるほどのことをした(ふつうの話・売り買い・手伝いは入れない)",
}
# 行動力の段ごとの、一日の行動量の目安(並は、十時間ほど働いて外に出た一日)。七日の上限はこの七倍
DAY_LOAD_PER_DAY = {"無": 0, "低": 18, "並": 30, "高": 42, "必": 54}
# 七日の行動量が上限のこの割合を超えると休みがちになり、上限で休む見込みが一番高くなる(人物の会話に聞かずに休む。おなかがすいていれば休まない)
DAY_REST_FROM_RATIO = 0.6
DAY_REST_MAX_CHANCE = 0.8
# 前の日の行動が無い人物の、日の始まりの空腹と人と触れ合いたい欲
DAY_INITIAL_HUNGER = 20
DAY_INITIAL_DESIRE = 0
# 人物の目に渡す、眠気・空腹・人と触れ合いたい欲・疲れの言い方。値がこの数より小さければ、その言い方
DAY_NEED_WORDS = {
    "眠気": ((30, "眠くない"), (60, "少し眠い"), (85, "眠い"), (101, "ひどく眠い")),
    "空腹": ((40, "おなかはすいていない"), (65, "少しおなかがすいた"), (85, "おなかがすいた"), (101, "ひどくおなかがすいた")),
    "人恋しさ": ((40, "落ち着いている"), (65, "少し人恋しい"), (85, "人恋しい"), (101, "ひどく人恋しい")),
    "疲れ": ((50, "元気"), (75, "少し疲れがたまっている"), (90, "疲れがたまっている"), (10000, "くたくたで、大きなことをする気が起きない")),
}
# 人物が見る、目の前にいる人物の上限
ACT_PRESENT_LIMIT = 10
# 動かしていない住人が留守にする時間(一日を 24 に割った刻みで、始まり〜終わりの手前)。昼は出かけていて住まいにいない
# (一日中住まいにいて手が空いている扱いだと、一人だけ動かす人物のまわりの世界が止まって見える)
DAY_RESIDENT_AWAY = (9, 18)
# 一日で生む人物・アイデアの上限(影響の枠がさらに絞る)
ACT_NEW_CHARACTER_LIMIT = 2
ACT_NEW_IDEA_LIMIT = 3
# 人物の目の段(一時間ごとの手・居合わせた相手への応じ)は数が多いので中くらいのモデルで回し、一日の記録だけを強いモデルで人物ごとに一回にする。
# 一番安いモデルでは、相手の一人称・口調が移った
ACT_MODEL = "claude-sonnet-5-5"
# 人物の目の段が返らなかったとき(安全装置に止められたときなど)に、一度だけやり直すモデル
ACT_FALLBACK_MODEL = "claude-haiku-5-5"
ACT_EFFORT = "low"
ACT_JUDGE_MODEL = "claude-opus-5-5"
ACT_JUDGE_EFFORT = "high"
# 一度に動かす人物の上限(人物ごとに、一時間ずつ並べて人物の目を回す)
DAY_CHARACTER_LIMIT = 8
# 記録する段に逆らわないよう渡す話。その日の前後この日数に、人物か居合わせた人物が出るプロットつきの話を、近い話から上限まで
ACT_NARRATOR_EPISODE_DAYS = 30
ACT_NARRATOR_EPISODE_LIMIT = 3
# 作者が親の出来事を置いた日に、記録する段に渡す筋。親から上へたどる先祖の数と、親の子のうちその日の前・後それぞれに渡す数
ACT_ARC_DEPTH_LIMIT = 12
ACT_ARC_SIBLING_LIMIT = 3
# 段(無/低/並/高/必)の並び。影響力を数で比べるのに使う
LEVEL_RANKS = {"無": 0, "低": 1, "並": 2, "高": 3, "必": 4}
# 主要人物は、影響力の値が低くてもこの段より下に扱わない(ほかの人物の一日から動かされにくくする)
MAIN_CHARACTER_MIN_INFLUENCE = "高"
# 影響の枠。動いた人物の影響力の段ごとに、来歴を残せる人数、居場所を移せる人数、生める人物・アイデアの数
ACT_IMPACT_PEOPLE = {"無": 1, "低": 2, "並": 3, "高": 5, "必": 8}
ACT_IMPACT_MOVES = {"無": 1, "低": 1, "並": 2, "高": 3, "必": 5}
ACT_IMPACT_NEW_CHARACTERS = {"無": 0, "低": 1, "並": 1, "高": 2, "必": 2}
ACT_IMPACT_IDEAS = {"無": 1, "低": 1, "並": 2, "高": 3, "必": 3}
# モチベーション(`character_motivation`)の強さの目安。人物の目と記録する段に、数と一緒に渡す
MOTIVATION_STRENGTHS = {
    1: "気にかかる程度", 2: "機会があればしたい", 3: "手間をかけてもしたい", 4: "ほかを後回しにしてもしたい",
    5: "何を捨てても果たしたい",
}
# 一人について材料に渡す、効いているモチベーションの上限(強い順)
ACT_MOTIVATION_LIMIT = 5
# 一日で足す・終えるモチベーションの上限(人数をまたいで数える。動いた人物の分を先に残す)
ACT_MOTIVATION_CHANGE_LIMIT = 6

# data_access_logic/character/knowledge.py(人物役が読む、自分が言ったセリフ)
# 言ってからこの日数までは原文、ここから鮮明の日数までは鮮明、それより後はあやふやを渡す。日は人物の暦の一日で数える
# (`character/time_sense.py`。一日 27 時間の暦なら 27 時間)
SPEECH_VERBATIM_DAYS = 3
SPEECH_VIVID_DAYS = 365

# data_access_logic/character/knowledge
# 人物役に渡す、本人が居合わせた出来事の件数(新しいほうから)。そのうち新しい `KNOWLEDGE_EVENT_TEXT_COUNT` 件は本文で、
# それより前は要約で渡す。出来事の本文は会話を写したもの(スキル `character-scenes`)で長く、全部を本文で渡すと材料が膨らむ
KNOWLEDGE_EVENT_LIMIT = 10
KNOWLEDGE_EVENT_TEXT_COUNT = 3
# 人物役に渡す、本人のモチベーションの件数。効いている行と終わった行を合わせて強い順に数え、終わった行は昔のモチベーションとして渡す
KNOWLEDGE_MOTIVATION_LIMIT = 10

# data_access_logic/episode_session/stage
# 語り部に渡す、話の前・後の出来事の件数の上限(それぞれ。話に近いほうから)。前は前の話の時刻から、後は次の話の時刻までに限る
STAGE_EVENT_LIMIT = 30
