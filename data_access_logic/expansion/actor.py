"""人物モード(`SimulateDay`)の AI だけの段。db に触らない。

人物一人に会話(エージェント)を一つ持たせ、その人物の一日を一つの会話で回す(`AIClient.session`)。一度目の問いに、一日のあいだ変わらない材料
(知っていること・思い・行ける場所・今日の予定)を渡し、二度目からは、その一時間の様子の差分だけを渡す(前の問いと答えは会話が覚えている)。
人物の目(人物役と同じ書き方の範囲)は中くらいのモデルで回す。一日の記録は作者の目(出来事の書き方の範囲)で、人物ごとに一度だけ強いモデルで回す。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from ai.instructions.materials import EVENT_PARTICIPANT_NOTE, LATER_EVENTS_NOTE, TIME_NOTE
from ai.instructions.naming import NAME_PLACEHOLDER
from data_access_logic import constants
from data_access_logic.ai_client import AIClient, AISession
from data_access_logic.expansion.act_models import (
    DayBrief, DayOutcomeDraft, DayPlace, DayRequest, HourDraft, HourScene, ReactionDraft,
)
from db.schema import StyleScope

logger = logging.getLogger(__name__)

_AGENT_SYSTEM = """\
あなたは物語の中の人物の一人として、一日を一時間ずつ過ごす。一時間ごとに、これからの一時間にすることを一つ決めて返す。
同じ場所に居合わせた人物のしたことを渡されたら、それを受けてどう応じるかを返す。
渡すのは、あなたが知っていることと、いま目の前にあることだけ。知らないこと(名を知らない人物の名前・素性、知らない出来事や事柄)を前提にしない。
あなたのミーム・行動原理・性格・来歴・関係とモチベーション、これまでにしたこと、体の具合から、いまこの時間にあなたが本当にしそうなことを決める。
人の一日は、眠る・食べる・働く・用事・人と話す・休むの積み重ねで、大きなことは一日にそう何度も起きない。ふだんの暮らしの一時間を、ふだんのとおりに過ごしてよい。
仕事や暮らしの決まった時間があれば、それに沿う。今日決まっている予定には間に合うように動き、先回りしない。
場所を移るなら、行ける場所の中から選ぶ。目の前の人物に話しかけてよい。応じるときは相手の言いなりにならなくてよく、気に留めずに自分のことを続けてもよい。
欠点・弱さ・悪意も、性格・来歴のとおりに丸めずに演じる。ほかの人物がどう応じるか、あなたの行動の結果どうなったかは書かない。
「体の具合」の空腹・眠気・人恋しさ・疲れは、人の体のとおりに効かせる。おなかがすけば食べ、眠ければ休み、疲れがたまっていれば大きなことを控える。
人恋しさは、親しい相手と寄り添う・手を取る・抱きしめるような触れ合いで満たす。相手の気持ちと間柄に沿う範囲だけで、書くのは見える仕草まで。
思いつきの元は、ほかの場面の筋の型。使うなら、あなたの立場と場所に合わせて形を変える。作者からの方向づけがあれば、言いなりにはならず、あなたらしい形で踏まえる。
「あなたのモチベーション」は、いまあなたが何をしたがっているかで、強さは 1(気にかかる程度)〜5(何を捨てても果たしたい)。
「あなたが関わったこれまでの出来事」は、あなたが居合わせて覚えていること。「この先に決まっている出来事」は、この先に起きると決まっていることで、
あなたはまだ知らない。あなたの言葉・内心に出さず、そこへ食い違わずにつながるように動き、それを先回りして起こさない。
「いつ」「いつから」は、いまからの隔たり(「3日前」「5日後」)。「いま」は今日の日付・時間帯で、年は渡さない。
内心と言葉に、物語の外のこと(作者・手番・時間の区切り)を書かない。言葉と内心は自分の口調・一人称・方言で書き、相手の話し方を移さない。"""


def agent(ai: AIClient) -> AISession:
    """人物一人の一日を回す会話。"""
    return ai.session(_AGENT_SYSTEM, StyleScope.ACTING, constants.ACT_MODEL, constants.ACT_EFFORT)


def _ask[Output: BaseModel](session: AISession, payload: dict[str, Any], request: str, output: type[Output],
                            name: str | None) -> Output | None:
    """返せなければ控えのモデルで一度だけやり直す(モデルの安全装置が、ふつうの人物のやり取りを止めることがある)。"""
    prompt = "\n".join([json.dumps(payload, ensure_ascii=False, indent=2), request])
    for model in dict.fromkeys([constants.ACT_MODEL, constants.ACT_FALLBACK_MODEL]):
        draft = session.ask(prompt, output, model=model)
        if draft is not None:
            return draft
        logger.warning(f"{name} の{output.__name__}が {model} で返らなかった")
    return None


def hour_draft(session: AISession, brief: DayBrief, scene: HourScene, seen_ids: set[int],
               first: list[DayPlace] | None = None, schedule: list[str] | None = None) -> HourDraft | None:
    """これからの一時間。`first` を渡したら一度目の問いとして、一日のあいだ変わらない材料と行ける場所・今日の予定を添える。
    `seen_ids` は会話の中で見た目を渡した人物(渡したあとに、今回渡す人物を足す)。"""
    payload = scene.for_prompt(brief.known_ids, seen_ids)
    seen_ids.update(person.character_id for person in scene.present)
    if first is not None:
        payload = {**brief.prompt, "行ける場所": [place.for_prompt() for place in first],
                   "今日決まっている予定": schedule or [], **payload}
    return _ask(session, payload, f"あなた({brief.name})の、これからの一時間を決める。", HourDraft, brief.name)


def reaction_draft(session: AISession, brief: DayBrief, others: list[str]) -> ReactionDraft | None:
    """`others` は居合わせた人物がこの一時間にしたこと(見る人の目で、名を知らない相手は伏せる)。決めていた一時間は会話が覚えている。"""
    return _ask(session, {"居合わせた人物がこの一時間にしたこと": others},
                f"あなた({brief.name})が決めていたこの一時間のうちに、居合わせた人物にどう応じるかを返す。", ReactionDraft, brief.name)


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


def judge_draft(ai: AIClient, request: DayRequest) -> DayOutcomeDraft | None:
    prompt = "\n".join([json.dumps(request.model_dump(), ensure_ascii=False, indent=2), "この人物の一日を記録する。"])
    outcome = ai.generate(prompt, DayOutcomeDraft, system=_JUDGE_SYSTEM, style_scope=StyleScope.EVENT,
                          model=constants.ACT_JUDGE_MODEL, effort=constants.ACT_JUDGE_EFFORT)
    if outcome is None:
        logger.warning(f"{request.actor_name}の一日の記録が得られなかった")
    return outcome
