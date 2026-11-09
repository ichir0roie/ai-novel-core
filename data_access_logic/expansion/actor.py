"""人物モード(`ActCharacter`)の AI だけの段。db に触らない。

語り部の段は、一手の前後に関わる話があるときだけ、狙う段の前に一手ごとに一度回す(語り部の書き方の範囲)。
前後の話のプロットを動機にし、プロットに逆らわないよう人物の外の状況を整え、裁く段に動機を残す。
狙う段と対話の手番は人物の目(人物役と同じ書き方の範囲)で、人物が知ることだけから一手を決める。数が多いので一番安いモデルで回す。
裁く段は作者の目(出来事の書き方の範囲)で、実行の中の手をまとめて一度だけ、サイコロの成り行きと影響の枠に沿って記録する。
"""
from __future__ import annotations

import json
import logging

from ai.instructions.materials import EVENT_PARTICIPANT_NOTE, LATER_EVENTS_NOTE, TIME_NOTE
from ai.instructions.naming import NAME_PLACEHOLDER
from data_access_logic import constants
from data_access_logic.ai_client import AIClient
from data_access_logic.event.writer import EVENT_TEXT_FORMAT
from data_access_logic.expansion.act_models import (
    ActorBrief, BatchOutcomeDraft, DialogueBrief, DialogueTurn, DialogueTurnDraft, IntentDraft, NarrationDraft,
    NarratorBrief, OutcomeRequest, OutcomeRequestSerialized,
)
from db.schema import StyleScope

logger = logging.getLogger(__name__)

# 人物の目の材料のうち、本人のモチベーションと前後の出来事(`act_models.Motives`)の読み方
_MOTIVES_NOTE = """\
「あなたのモチベーション」は、いまあなたが何をしたがっているかで、強さは 1(気にかかる程度)〜5(何を捨てても果たしたい)。
「あなたが関わったこれまでの出来事」は、あなたが居合わせて覚えていること。
「この先に決まっている出来事」は、この先に起きると決まっていることで、あなたはまだ知らない。
あなたの言葉・内心に出さず、そこへ食い違わずにつながるように動き、それを先回りして起こさない。"""

_NARRATOR_SYSTEM = """\
あなたは物語の語り部として、ある人物がこれから打つ一手の前に場を整える。
渡すのは、一手の時刻・場所・動く人物・居合わせる人物・この場所で近ごろ起きたことと、その前後にある、この人物たちが出る話のプロット。
プロットは作者が決めた筋。あなたの動機は、この一手をプロットに逆らわせないこと。プロットの場面で起きることを先に起こさせず、
プロットの前提(誰がどこにいて、何を持ち、誰と知り合いか)を崩させず、プロットに出る人物をその場面に出られなくさせない。
本文のある話は、プロットのとおりに起きたこととして扱う。
人物が何を思い、どう動くかは人物が決める。あなたが動かしてよいのは、人物の外のこと(人の出入り・用事・知らせ・天気・道・物の在り処)だけ。
narration と request は人物に渡る。人物がその場で見聞きできることだけを書き、プロットそのもの・先の筋・人物の知らない人物の名前・素性・秘密を書かない。"""

_INTENT_SYSTEM = f"""\
あなたは物語の中の人物の一人として、次の一手を決める。渡すのは、あなたが知っていることと、いま目の前にあることだけ。
知らないこと(名を知らない人物の名前・素性、知らない出来事や事柄)を前提にしない。
これまでの出来事の続きとして、モチベーションのどれを果たしに・近づきに動くかを、強さと目の前の様子から考える。
強い思いほど先にするが、目の前の機会や危うさで、弱い思いを先にしてもよい。沿ったモチベーションの id を motivation_id に書く。
あなたのミーム・行動原理・性格・来歴・関係から、いまこの場であなたが本当にしそうなことを一つ決める。
企てを追っているなら、それを続けるか、別のことをするかを、あなた自身の考えで選ぶ。
思いつきの元は、ほかの場面の筋の型。使うなら、あなたの立場と場所に合わせて形を変える。
作者からの方向づけがあれば、それを踏まえる(言いなりにはならず、あなたらしい形で)。
語り部の語りは、いま目の前で起きたこととして受ける。語り部の要求は、あなたが自分で決めたこととして演じ、言い回しと理由を自分で埋める。
あなたのミーム・行動原理・性格とぶつかるときだけ断ってよい(断るなら、内心にその理由を書く)。
一手は、一日から数日で片の付く大きさにする。大きな企ては、その最初の一手だけを決め、企ての名前を付ける。
目の前の相手と言葉を交わして決めたいことがあれば、その相手を invites に挙げる。挙げてよいのは、目の前にいて名前を知っている人物だけ。

{_MOTIVES_NOTE}"""

_TURN_SYSTEM = f"""\
あなたは物語の中の人物の一人として、目の前のやり取りに一手を返す。渡すのは、あなたが知っていることと、目の前の様子と、
ここまでに見聞きしたことだけ。知らないこと(名を知らない人物の名前・素性、知らない出来事や事柄)を前提にしない。
あなたのミーム・行動原理・性格・来歴・関係とモチベーションから、この場であなたが本当にしそうなことを決める。相手の言いなりにならなくてよく、断ってもよい。
欠点・弱さ・悪意も、性格・来歴のとおりに丸めずに演じる。
ほかの人物がどう応じるか、あなたの行動の結果どうなったかは書かない。言いたいことを言い、動き、相手の返事を待つところで止める。
内心と狙いに、物語の外のこと(作者・手番・要求)を書かない。言葉と内心は「自分」の口調・一人称・方言で書く。

{_MOTIVES_NOTE}"""

_JUDGE_SYSTEM = f"""\
物語の人物たちが、それぞれ一手を打った。手ごとに、場所の状況、人物の内心と狙い・行動、巻きこんだ相手とのやり取り、
サイコロで決まった成り行き、影響の枠を渡すので、その手がその場所・時点で起こしたことを、手ごとに出来事として1件ずつ記録に起こす。
手は時刻の順に並べてある。前の手で起きたことは、後の手の場所・人物の様子として扱い、食い違わせない。
成り行きに沿わせる(狙いがいつも通るとは限らない)。巻きこんだ相手とのやり取りは、言葉どおりに起きたこととして記録に入れる。
影響の枠に収める。character_updates の人数・character_moves の人数・new_characters・ideas は枠の数まで。
「動かされにくい人物」の character_updates と character_moves は書かない。場所をなくす・作るのは、枠で「できる」ときだけ。
event_text は、人物の行動と、居合わせた人物・対象の反応を起きた順に書く。id ではなく名前で書く。
character_ids は、関わった人物・対象の人物idを、その手の居合わせる人物・対象の中からだけ選ぶ。動いた人物も入れる。
character_moves は、この出来事で住まい・拠点が変わった人物ごとの移動先。場所idはその手の移動先の候補からだけ選ぶ。一時の外出は入れない。
location_abolished / location_founded は、この出来事が場所自身の消滅・新設に及ぶときだけ埋める。ほかは false / null。
character_updates の text は、この出来事で新しく分かった、その人物の性格・信念(人物以外なら性質・方針)を一文で書く。この時刻の来歴に一文として足される。新しく分かったことの無い人物は含めない。その人物を指すときは名前を書かず「{NAME_PLACEHOLDER}」と書く。
ideas は、この一手で新しく生まれた・広まった事柄(技術・制度・概念・呼び名・噂など)だけ。人名・地名は入れない。knower_ids は、それを知った人物をその手の居合わせる人物・対象の中から選ぶ。
new_characters は、この一手で新しく世界に現れる人物・対象(生まれた子・雇った者・作った組織など)だけ。居合わせる人物・対象は入れない。
arc_closed は、続けた企てがあり、この一手でそれが果たされたか潰えたときだけ true。
motivation_changes は、この一手のあとの、居合わせる人物の思い(モチベーション)の動き。強さは 1(気にかかる程度)〜5(何を捨てても果たしたい)。
新しく生まれた思いは motivation_id を null にし、内容と強さを書く。強まった・弱まった思いは、そのモチベーションid と新しい強さを書き、text は null。
果たした・消えた思いは、そのモチベーションid と強さ 0。モチベーションid は「居合わせる人物のモチベーション」のその人物の行からだけ選ぶ。
動いた人物の、一手が沿った思いを先に見る(成り行きで果たした・弱まった・かえって強まった)。変わらない思いは入れない。
「動かされにくい人物」の思いは書かない。
「語り部の動機」のある手は、前後の話のプロットに逆らう記録にしない。プロットの場面で起きることを先に起こさず、プロットの前提
(誰がどこにいて、何を持ち、誰と知り合いか)を崩さず、プロットに出る人物をその場面に出られなくしない。成り行きがプロットとぶつかるときは、
プロットに逆らわない形で成り行きを起こす(しくじる・遅れる・別の困りごとが起きる)。語り部の語りは、その場で起きたこととして記録に入れる。

{EVENT_TEXT_FORMAT}

{EVENT_PARTICIPANT_NOTE}

{LATER_EVENTS_NOTE}

{TIME_NOTE}"""


def narration_draft(ai: AIClient, brief: NarratorBrief) -> NarrationDraft | None:
    prompt = "\n".join([json.dumps(brief.prompt, ensure_ascii=False, indent=2),
                        "前後の話のプロットに逆らわないよう、この一手の前に場を整える。"])
    draft = ai.generate(prompt, NarrationDraft, system=_NARRATOR_SYSTEM, style_scope=StyleScope.NARRATOR,
                        model=constants.ACT_NARRATOR_MODEL, effort=constants.ACT_NARRATOR_EFFORT)
    if draft is None:
        logger.warning("語り部の動機が得られなかった")
    return draft


def intent_draft(ai: AIClient, brief: ActorBrief) -> IntentDraft | None:
    prompt = "\n".join([json.dumps(brief.prompt, ensure_ascii=False, indent=2), "あなたの次の一手を決める。"])
    intent = ai.generate(prompt, IntentDraft, system=_INTENT_SYSTEM, style_scope=StyleScope.ACTING,
                         model=constants.ACT_MODEL, effort=constants.ACT_EFFORT)
    if intent is None:
        logger.warning("人物の一手が得られなかった")
    return intent


def turn_draft(ai: AIClient, brief: DialogueBrief, seen: list[DialogueTurn], request: str) -> DialogueTurn | None:
    """対話の手番を一つ。`seen` は、この人物がここまでに見聞きした手番(起きた順)。"""
    prompt = "\n".join([
        json.dumps({**brief.prompt,
                    "ここまでに見聞きしたこと(起きた順)": [turn.seen_by(brief.character_id, brief.known_ids)
                                                    for turn in seen],
                    "求められていること": request}, ensure_ascii=False, indent=2),
        "あなたの一手を返す。",
    ])
    draft = ai.generate(prompt, DialogueTurnDraft, system=_TURN_SYSTEM, style_scope=StyleScope.ACTING,
                        model=constants.ACT_MODEL, effort=constants.ACT_EFFORT)
    if draft is None:
        logger.warning(f"{brief.name}(id={brief.character_id})の手番が得られなかった")
        return None
    return DialogueTurn(character_id=brief.character_id, name=brief.name, thought=draft.thought, action=draft.action,
                        speech=draft.speech, aim=draft.aim, done=draft.done)


def judge_draft(ai: AIClient, requests: list[OutcomeRequest]) -> BatchOutcomeDraft | None:
    """実行の中の手をまとめて裁く。手の番号は `requests` の並び(1 始まり)。"""
    acts = [{"手の番号": number, **OutcomeRequestSerialized.model_validate(request.model_dump()).model_dump()}
            for number, request in enumerate(requests, start=1)]
    prompt = "\n".join([json.dumps({"手": acts}, ensure_ascii=False, indent=2),
                        "手ごとに、その手がその場所・時点で起こしたことを記録する。"])
    outcome = ai.generate(prompt, BatchOutcomeDraft, system=_JUDGE_SYSTEM, style_scope=StyleScope.EVENT,
                          model=constants.ACT_JUDGE_MODEL, effort=constants.ACT_JUDGE_EFFORT)
    if outcome is None:
        logger.warning("手の記録が得られなかった")
    return outcome
