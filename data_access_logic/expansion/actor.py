"""人物モード(`SimulateDay`)の AI だけの段。db に触らない。

一時間ごとの手と居合わせた相手への応じは人物の目(人物役と同じ書き方の範囲)で、人物が知ることと目の前の様子だけから決める。
数が多いので中くらいのモデルで回す。一日の記録は作者の目(出来事の書き方の範囲)で、人物ごとに一度だけ強いモデルで回す。
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from ai.instructions.materials import EVENT_PARTICIPANT_NOTE, LATER_EVENTS_NOTE, TIME_NOTE
from ai.instructions.naming import NAME_PLACEHOLDER
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.expansion.act_models import (
    DayBrief, DayOutcomeDraft, DayRequest, HourDraft, HourScene, ReactionDraft,
)
from db.schema import StyleScope

logger = logging.getLogger(__name__)

# 人物の目の材料のうち、本人のモチベーションと前後の出来事(`act_models.Motives`)と体の具合の読み方
_MOTIVES_NOTE = """\
「あなたのモチベーション」は、いまあなたが何をしたがっているかで、強さは 1(気にかかる程度)〜5(何を捨てても果たしたい)。
「あなたが関わったこれまでの出来事」は、あなたが居合わせて覚えていること。
「この先に決まっている出来事」は、この先に起きると決まっていることで、あなたはまだ知らない。
「いつ」「いつから」は、いまからの隔たり(「3日前」「5日後」)。「いま」は今日の日付・時間帯で、年は渡さない。
あなたの言葉・内心に出さず、そこへ食い違わずにつながるように動き、それを先回りして起こさない。
「体の具合」の眠気・空腹は、人の体のとおりに効かせる。眠ければ休むか眠り、おなかがすけば食べる。"""

_HOUR_SYSTEM = f"""\
あなたは物語の中の人物の一人として、これからの一時間にすることを一つ決める。渡すのは、あなたが知っていることと、いま目の前にあることだけ。
知らないこと(名を知らない人物の名前・素性、知らない出来事や事柄)を前提にしない。
あなたのミーム・行動原理・性格・来歴・関係とモチベーション、今日これまでにしたこと、体の具合から、いまこの時間にあなたが本当にしそうなことを決める。
人の一日は、眠る・食べる・働く・用事・人と話す・休むの積み重ねで、大きなことは一日にそう何度も起きない。ふだんの暮らしの一時間を、ふだんのとおりに過ごしてよい。
仕事や暮らしの決まった時間があれば、それに沿う。今日このあと決まっている予定があれば、それに間に合うように動き、先回りしない。
場所を移るなら、行ける場所の中から選ぶ。目の前の人物に話しかけてよい。
思いつきの元は、ほかの場面の筋の型。使うなら、あなたの立場と場所に合わせて形を変える。作者からの方向づけがあれば、言いなりにはならず、あなたらしい形で踏まえる。
内心と言葉に、物語の外のこと(作者・手番・時間の区切り)を書かない。言葉と内心は自分の口調・一人称・方言で書く。

{_MOTIVES_NOTE}"""

_REACTION_SYSTEM = f"""\
あなたは物語の中の人物の一人として、この一時間に同じ場所に居合わせた人物のしたこと・言ったことを受けて、どう応じるかを決める。
渡すのは、あなたが知っていることと、目の前の様子と、あなたが決めていたこの一時間の過ごし方と、居合わせた人物がしたことだけ。
知らないこと(名を知らない人物の名前・素性、知らない出来事や事柄)を前提にしない。
あなたのミーム・行動原理・性格・来歴・関係とモチベーションから、この場であなたが本当にしそうな応じ方を決める。相手の言いなりにならなくてよく、
気に留めずに自分のことを続けてもよい。欠点・弱さ・悪意も、性格・来歴のとおりに丸めずに演じる。
ほかの人物がどう応じるか、あなたの行動の結果どうなったかは書かない。
内心に物語の外のこと(作者・手番)を書かない。言葉と内心は自分の口調・一人称・方言で書き、相手の話し方を移さない。

{_MOTIVES_NOTE}"""

_JUDGE_SYSTEM = f"""\
物語の人物の一人が、一日を一時間ずつ過ごした。その日の行動(どこで何をし、誰と居合わせて何を言い合ったか)を渡すので、
その人物の一日を、出来事として一件の記録に起こす。
行動は起きたこととして扱い、書き足しも書き替えもしない。眠る・食べるだけの時間はまとめて短く書き、人と居合わせた場面・用事・仕事で起きたことを中心に書く。
人と言い合ったことは、言葉どおりに記録に入れる。
影響の枠に収める。character_updates の人数・character_moves の人数・new_characters・ideas は枠の数まで。
「動かされにくい人物」の character_updates と character_moves は書かない。
event_text は、人物の行動と、居合わせた人物・対象の反応を起きた順に書く。id ではなく名前で書く。居合わせた人物みなが読むので、人物の内心は書かない(見えた行動と聞こえた言葉だけ)。
居合わせた人物と来歴はそのまま人物に渡るので、event_text と character_updates に年・日付(暦の時刻)を書かない。時の移りは「朝」「昼すぎ」「夜ふけ」のような時間帯で書く。
character_ids は、その日に関わった人物・対象の人物idを、居合わせた人物の中からだけ選ぶ。動いた人物も入れる。
character_moves は、この一日で住まい・拠点が変わった人物ごとの移動先。場所idは移動先の候補からだけ選ぶ。一時の外出は入れない。
character_updates の text は、この一日で新しく分かった、その人物の性格・信念(人物以外なら性質・方針)を一文で書く。その日の来歴に一文として足される。新しく分かったことの無い人物は含めない。その人物を指すときは名前を書かず「{NAME_PLACEHOLDER}」と書く。
ideas は、この一日で新しく生まれた・広まった事柄(技術・制度・概念・呼び名・噂など)だけ。人名・地名は入れない。knower_ids は、それを知った人物を居合わせた人物の中から選ぶ。
new_characters は、この一日で新しく世界に現れる人物・対象(雇った者・作った組織など)だけ。居合わせた人物は入れない。
motivation_changes は、この一日のあとの、居合わせた人物の思い(モチベーション)の動き。強さは 1(気にかかる程度)〜5(何を捨てても果たしたい)。
新しく生まれた思いは motivation_id を null にし、内容と強さを書く。強まった・弱まった思いは、そのモチベーションid と新しい強さを書き、text は null。
果たした・消えた思いは、そのモチベーションid と強さ 0。モチベーションid は「居合わせた人物のモチベーション」のその人物の行からだけ選ぶ。
変わらない思いは入れない。「動かされにくい人物」の思いは書かない。
「作者が置いた筋」と「前後の話」に逆らう記録にしない。話の場面で起きることを先に起こさず、話の前提(誰がどこにいて、何を持ち、誰と知り合いか)を崩さない。
行動が筋とぶつかるときは、筋に逆らわない形で記録する(しくじる・遅れる・別の困りごとが起きる)。

{EVENT_PARTICIPANT_NOTE}

{LATER_EVENTS_NOTE}

{TIME_NOTE}"""


def _acting[Output: BaseModel](ai: AIClient, prompt: str, output: type[Output], system: str) -> Output | None:
    """人物の目の段。返せなければ控えのモデルで一度だけやり直す(モデルの安全装置が、ふつうの人物のやり取りを止めることがある)。"""
    for model in dict.fromkeys([constants.ACT_MODEL, constants.ACT_FALLBACK_MODEL]):
        draft = ai.generate(prompt, output, system=system, style_scope=StyleScope.ACTING, model=model,
                            effort=constants.ACT_EFFORT)
        if draft is not None:
            return draft
        logger.warning(f"{model} で人物の目の段({output.__name__})が返らなかった")
    return None


def _material(brief: DayBrief, scene: HourScene) -> dict:
    return {**brief.prompt, **scene.for_prompt(brief.known_ids)}


def hour_draft(ai: AIClient, brief: DayBrief, scene: HourScene) -> HourDraft | None:
    prompt = "\n".join([json.dumps(_material(brief, scene), ensure_ascii=False, indent=2),
                        f"あなた({brief.name})の、これからの一時間を決める。"])
    draft = _acting(ai, prompt, HourDraft, _HOUR_SYSTEM)
    if draft is None:
        logger.warning(f"{brief.name}(id={brief.character_id})の一時間が得られなかった")
    return draft


def reaction_draft(ai: AIClient, brief: DayBrief, scene: HourScene, planned: str, others: list[str]) -> ReactionDraft | None:
    """`planned` は本人が決めていたこの一時間、`others` は居合わせた人物がこの一時間にしたこと(見る人の目で、名を知らない相手は伏せる)。"""
    prompt = "\n".join([
        json.dumps({**_material(brief, scene), "あなたが決めていたこの一時間": planned,
                    "居合わせた人物がこの一時間にしたこと": others}, ensure_ascii=False, indent=2),
        # 相手の言葉を読んだすぐあとに書くので、相手の一人称・口調が移りやすい
        f"あなた({brief.name})の応じ方を返す。一人称・口調は自分の話し方のとおりにし、相手の話し方を移さない。",
    ])
    draft = _acting(ai, prompt, ReactionDraft, _REACTION_SYSTEM)
    if draft is None:
        logger.warning(f"{brief.name}(id={brief.character_id})の応じ方が得られなかった")
    return draft


def judge_draft(ai: AIClient, request: DayRequest) -> DayOutcomeDraft | None:
    prompt = "\n".join([json.dumps(request.model_dump(), ensure_ascii=False, indent=2), "この人物の一日を記録する。"])
    outcome = ai.generate(prompt, DayOutcomeDraft, system=_JUDGE_SYSTEM, style_scope=StyleScope.EVENT,
                          model=constants.ACT_JUDGE_MODEL, effort=constants.ACT_JUDGE_EFFORT)
    if outcome is None:
        logger.warning(f"{request.actor_name}の一日の記録が得られなかった")
    return outcome
