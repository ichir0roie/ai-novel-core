"""人物モード(`ActCharacter`)の AI だけの段。db に触らない。

狙う段は人物の目(人物役と同じ書き方の範囲)で、人物が知ることだけから一手を決める。
裁く段は作者の目(出来事の書き方の範囲)で、その一手が世界に起こしたことを、サイコロの成り行きに沿って記録する。
"""
from __future__ import annotations

import json
import logging

from ai.instructions.materials import EVENT_PARTICIPANT_NOTE, LATER_EVENTS_NOTE, TIME_NOTE
from ai.instructions.naming import NAME_PLACEHOLDER
from data_access_logic.ai_client import AIClient
from data_access_logic.event.writer import EVENT_TEXT_FORMAT
from data_access_logic.expansion.act_models import (
    ActOutcomeDraft, ActorBrief, IntentDraft, OutcomeRequest, OutcomeRequestSerialized,
)
from db.schema import StyleScope

logger = logging.getLogger(__name__)

_INTENT_SYSTEM = """\
あなたは物語の中の人物の一人として、次の一手を決める。渡すのは、あなたが知っていることと、いま目の前にあることだけ。
知らないこと(名を知らない人物の名前・素性、知らない出来事や事柄)を前提にしない。
あなたのミーム・行動原理・性格・来歴・関係から、いまこの場であなたが本当にしそうなことを一つ決める。
企てを追っているなら、それを続けるか、別のことをするかを、あなた自身の考えで選ぶ。
思いつきの元は、ほかの場面の筋の型。使うなら、あなたの立場と場所に合わせて形を変える。
作者からの方向づけがあれば、それを踏まえる(言いなりにはならず、あなたらしい形で)。
一手は、一日から数日で片の付く大きさにする。大きな企ては、その最初の一手だけを決め、企ての名前を付ける。"""

_OUTCOME_SYSTEM = f"""\
物語の人物が一手を打った。場所の状況、人物の内心と狙い・行動、サイコロで決まった成り行きを渡すので、
その一手がこの場所・時点で起こしたことを、出来事として1件、記録に起こす。成り行きに沿わせる(狙いがいつも通るとは限らない)。
event_text は、人物の行動と、居合わせた人物・対象の反応を起きた順に書く。id ではなく名前で書く。
character_ids は、関わった人物・対象の人物idを、居合わせる人物・対象の中からだけ選ぶ。動いた人物も入れる。
character_moves は、この出来事で住まい・拠点が変わった人物ごとの移動先。場所idは移動先の候補からだけ選ぶ。一時の外出は入れない。
location_abolished / location_founded は、この出来事が場所自身の消滅・新設に及ぶときだけ埋める。ほかは false / null。
character_updates の text は、この出来事で新しく分かった、その人物の性格・信念(人物以外なら性質・方針)を一文で書く。この時刻の来歴に一文として足される。新しく分かったことの無い人物は含めない。その人物を指すときは名前を書かず「{NAME_PLACEHOLDER}」と書く。
ideas は、この一手で新しく生まれた・広まった事柄(技術・制度・概念・呼び名・噂など)だけ。人名・地名は入れない。knower_ids は、それを知った人物を居合わせる人物・対象の中から選ぶ。
new_characters は、この一手で新しく世界に現れる人物・対象(生まれた子・雇った者・作った組織など)だけ。居合わせる人物・対象は入れない。
arc_closed は、続けた企てがあり、この一手でそれが果たされたか潰えたときだけ true。

{EVENT_TEXT_FORMAT}

{EVENT_PARTICIPANT_NOTE}

{LATER_EVENTS_NOTE}

{TIME_NOTE}"""


def intent_draft(ai: AIClient, brief: ActorBrief) -> IntentDraft | None:
    prompt = "\n".join([json.dumps(brief.prompt, ensure_ascii=False, indent=2), "あなたの次の一手を決める。"])
    intent = ai.generate(prompt, IntentDraft, system=_INTENT_SYSTEM, style_scope=StyleScope.ACTING)
    if intent is None:
        logger.warning("人物の一手が得られなかった")
    return intent


def outcome_draft(ai: AIClient, request: OutcomeRequest) -> ActOutcomeDraft | None:
    prompt = "\n".join([
        OutcomeRequestSerialized.model_validate(request.model_dump()).model_dump_json(indent=2),
        "この一手がこの場所・時点で起こしたことを記録する。",
    ])
    outcome = ai.generate(prompt, ActOutcomeDraft, system=_OUTCOME_SYSTEM, style_scope=StyleScope.EVENT)
    if outcome is None:
        logger.warning("一手の記録が得られなかった")
    return outcome
