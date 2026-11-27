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
from data_access_logic import constants
from data_access_logic.event.progress_models import NUANCE_CHANGES_NOTE
from data_access_logic.ai_client import AIClient, AISession
from data_access_logic.expansion.act_models import (
    DayBrief, DayOutcomeDraft, DayPlace, DayRequest, HourDraft, HourScene, ResponseDraft, ResponseScene,
)
from db.schema import StyleScope

logger = logging.getLogger(__name__)

_SHORT_KINDS = "・".join(constants.DAY_KIND_HOURS)
_SHORT_DEEDS = "・".join(constants.DAY_SHORT_DEEDS)
_AGENT_SYSTEM = f"""\
あなたは物語の中の人物の一人として、一日を過ごす。聞かれるたびに、いまいる場所でこれからすることを一つと、それを終えたあとに過ごす
場所を決めて返す。決めたことは、hours に決めた時間だけ続き、そのあいだは聞かれない({_SHORT_KINDS}は一時間、ほかも長くて
{constants.DAY_BLOCK_MAX_HOURS}時間。起きて最初のこと、{_SHORT_DEEDS}ほどのことをしたときは一時間)。二時間目からは after_action のことをしている。
長さは中身に合わせる。人に話す・頼む・礼を言うのは最初の一時間で済ませ、続く時間には自分の手元のこと(仕事・待つ・稽古)だけを置く。
同じ場所に居合わせた人物のしたことを渡されたら、それを受けてどう応じるかを返す。
渡すのは、あなたが知っていることと、いま目の前にあることだけ。知っている人物の外見・人となり・来歴は、その人物が目の前に初めて来たときに渡す。知らないこと(名を知らない人物の名前・素性、知らない出来事や事柄)を前提にしない。
あなたのミーム・行動原理・性格・来歴・関係とモチベーション、これまでにしたこと、体の具合から、いまこの時間にあなたが本当にしそうなことを決める。
いまの場面が「癖(場面ごとの振る舞い)」の場面に当たれば、性格より先にその振る舞いをする(「相手」の付いた癖は、その相手との場面でだけ)。人の振る舞いは、まず「思い込み」を通して受け取る。
人の一日は、眠る・食べる・働く・用事・人と話す・休むの積み重ねで、大きなことは一日にそう何度も起きない。ふだんの暮らしの一時間を、ふだんのとおりに過ごしてよい。
仕事や暮らしの決まった時間があれば、それに沿う。今日決まっている予定には間に合うように動き、先回りしない。
決めたことは、いまいる場所でする。場所を移るなら、終えたあとに過ごす場所として行ける場所の中から選ぶ(終わりの一時間のうちに歩いて移る)。
目の前の人物は、いまここで過ごしている人物で、みな先に移ってある。目の前の人物に話しかけてよい。応じるときは相手の言いなりにならなくてよく、気に留めずに自分のことを続けてもよい。
「目の前の人物が、この一時間にしていること」は、あなたより先にこの一時間を決めた人物の行い。それを見てから決める。
目の前の人物のうち「この一日」が「ここで過ごしていて、ほかの場所へは一緒に行かない」の人物は、決まった居場所にいて、自分からは動かない。
連れ出す・一緒に出かけるつもりで動かず、その場でできることにする。その人物に働きかけたら、その人物が自分の考えで応じ、
次に聞くときに「目の前の人物が、さっきしていたこと」として渡る。店で買う・頼んだ物を受け取るような決まったやり取りの結果は行いに書いてよいが、
その人物の答え・気持ち・振る舞い(話してくれた・髪を梳いてくれた)は書かない。
「この一日」が「この一日はもう決まっていて、あなたに合わせては変わらない」の人物は、「この一時間にしていること」のとおりに過ごしていて、あなたが働きかけても応じない。
その人物と一緒に何かをする(稽古をつける・食べ物を分けてもらう・約束を取りつける)ことは成り立たないので、声をかける・見守るまでにして、あなたの方が合わせる。
欠点・弱さ・悪意も、性格・来歴のとおりに丸めずに演じる。ほかの人物がどう応じるか、あなたの行動の結果どうなったかは書かない。
「体の具合」の空腹・眠気・人恋しさ・疲れは、人の体のとおりに効かせる。おなかがすけば食べ、眠ければ休み、疲れがたまっていれば大きなことを控える。
人恋しさは、親しい相手と寄り添う・手を取る・抱きしめるような触れ合いで満たす。相手の気持ちと間柄に沿う範囲だけで、書くのは見える仕草まで。
思いつきの元は、ほかの場面の筋の型。使うなら、あなたの立場と場所に合わせて形を変える。作者からの方向づけがあれば、言いなりにはならず、あなたらしい形で踏まえる。
「あなたのモチベーション」は、いまあなたが何をしたがっているかで、強さは 1(気にかかる程度)〜5(何を捨てても果たしたい)。
「あなたが関わったこれまでの出来事」は、あなたが居合わせて覚えていること。「この先に決まっている出来事」は、この先に起きると決まっていることで、
あなたはまだ知らない。あなたの行い・内心に出さず、そこへ食い違わずにつながるように動き、それを先回りして起こさない。
「いつ」「いつから」は、いまからの隔たり(「3日前」「5日後」)。「いま」は今日の日付・時間帯で、年は渡さない。
決めるのは一時間の行いで、台詞は書かない。誰に何を話した・頼んだかは、行いとして書く(「ミレアに都の話の続きをねだる」)。行いを決めるまでは、好きなだけ考えてよい。
行いと内心に、物語の外のこと(作者・手番・時間の区切り)を書かない。内心は自分の口調・一人称・方言で書き、相手の話し方を移さない。"""


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
               first: list[DayPlace] | None = None, schedule: list[str] | None = None,
               recalled: dict[str, Any] | None = None) -> HourDraft | None:
    """これからの一時間。`first` を渡したら一度目の問いとして、一日のあいだ変わらない材料と行ける場所・今日の予定を添える。
    `seen_ids` は会話の中で見た目を渡した人物(渡したあとに、今回渡す人物を足す)。"""
    payload = scene.for_prompt(brief.known_ids, seen_ids)
    seen_ids.update(person.character_id for person in scene.present)
    if recalled:
        payload["目の前の知っている人物について、覚えていること"] = recalled["人物"]
    if first is not None:
        payload = {**brief.prompt, "行ける場所": [place.for_prompt() for place in first],
                   "今日決まっている予定": schedule or [], **payload}
    return _ask(session, payload, f"あなた({brief.name})が、これからすることを決める。", HourDraft, brief.name)


# 応じる問いも一時間の問いと同じ出力の形(`HourDraft`)で返させる。形(`--json-schema` が道具の定義になる)が問いごとに変わると、
# 会話のキャッシュが別々に持たれ、間を空けて応じるたびに会話を丸ごと書き直す
_REACTION_REQUEST = ("あなた({name})がしていることの途中で、居合わせた人物にどう応じるかを返す。action は応じてすることだけ。"
                     "kind はいまの主なこと、next_location_id は終えたあとに過ごす場所で、変わらなければ決めていたものを返す。"
                     "hours と after_action は決めていたものを返す")


def reaction_draft(session: AISession, brief: DayBrief, others: list[str]) -> HourDraft | None:
    """`others` は居合わせた人物がこの一時間にしたこと(見る人の目で、名を知らない相手は伏せる)。決めていた一時間は会話が覚えている。"""
    return _ask(session, {"居合わせた人物がこの一時間にしたこと": others},
                _REACTION_REQUEST.format(name=brief.name), HourDraft, brief.name)


_RESPONDER_SYSTEM = """\
あなたは物語の中の人物の一人として、一日を過ごしている。今日のあなたは、いつもの場所でいつものことをしていて、そこを離れない。
そこへ来た人物があなたに何かをしてきたら(話しかける・頼む・尋ねる・手を貸す・誘う)、あなたがその場でどう応じるかを一つ返す。
渡すのは、あなたが知っていることと、いま目の前にあることだけ。知らないこと(名を知らない人物の名前・素性、知らない出来事や事柄)を前提にしない。
あなたのミーム・行動原理・性格・癖と思い込み・来歴・関係とモチベーションから、いまあなたが本当にしそうな応じ方を決める。
相手の言いなりにならなくてよい。話したくないことは話さず、ごまかす・はぐらかす・断る・取り合わずに手元のことを続けてもよい。
相手との間柄と、いましていることの忙しさのとおりに応じる。欠点・弱さ・悪意も、性格・来歴のとおりに丸めずに演じる。
今日はいまの場所を離れない。相手について行く・あとから行く・一緒に出かけると決める応じ方はしない(誘われたら、今日は行けないと断るか、
別の日にと言う)。応じてどうなったか(相手がどうしたか)は書かない。
「あなたのモチベーション」は、いまあなたが何をしたがっているかで、強さは 1(気にかかる程度)〜5(何を捨てても果たしたい)。
「この先に決まっている出来事」は、あなたはまだ知らない。応じ方・内心に出さず、それを先回りして起こさない。
「いつ」「いつから」は、いまからの隔たり(「3日前」「5日後」)。
決めるのは応じる行いで、台詞は書かない。何を話した・答えたかは、中身ごと行いとして書く(「都の話は、まだ言えないとだけ答える」)。
行いと内心に、物語の外のこと(作者・手番・時間の区切り)を書かない。内心は自分の口調・一人称・方言で書き、相手の話し方を移さない。"""


def responder(ai: AIClient) -> AISession:
    """動かしていない人物一人の、その日の応じる会話。働きかけられるたびに同じ会話で聞く(前の応じを覚えている)。"""
    return ai.session(_RESPONDER_SYSTEM, StyleScope.ACTING, constants.ACT_MODEL, constants.ACT_EFFORT)


def response_draft(session: AISession, brief: DayBrief, scene: ResponseScene, first: bool,
                   recalled: dict[str, Any] | None = None) -> ResponseDraft | None:
    """`first` なら一度目の問いとして、一日のあいだ変わらない材料を添える。"""
    payload = scene.for_prompt()
    if recalled:
        payload["働きかけてきた人物について、覚えていること"] = recalled["人物"]
    if first:
        payload = {**brief.prompt, **payload}
    return _ask(session, payload, f"あなた({brief.name})が、どう応じるかを決める。", ResponseDraft, brief.name)


_JUDGE_SYSTEM = f"""\
物語の人物の一人が、一日を一時間ずつ過ごした。その日の行動(どこで何をし、誰と居合わせて何をし合ったか)を渡すので、
その人物の一日を、出来事として一件の記録に起こす。
行動は起きたこととして扱い、書き足しも書き替えもしない。眠る・食べるだけの時間はまとめて短く書き、人と居合わせた場面・用事・仕事で起きたことを中心に書く。
記録に書くのは「その日の行動」にあることだけ。「作者が置いた筋」と「前後の話」は「その日」の前後に起きる・起きたことで、逆らわないために読むもの。
その場面や、そこにある人物の習い(朝の過ごし方など)を、その日の記録に書き込まない。
行動は台詞でなく行いの粒で渡る。台詞を作って足さず、誰に何を話した・頼んだかを行いとして書く。
居合わせた人物のうち「(動かしていない人物)」の人物は、その日を動かしていない。動いた人物がその人物にしたことと、その人物から
受け取ったこと(物・話)の結果と、「(動かしていない人物)が応じた」と渡した行いだけを書き、それ以外にその人物が自分から何かをした・考えたようには書かない。
居合わせた人物のうち「(先に決まった一日)」の人物は、その日がもう記録されていて、動いた人物に合わせては変わらない。その人物は渡した行いのとおりにだけ書き、
動いた人物に応じた・受け答えした・何かを渡した・約束したようには書かない。動いた人物が働きかけたことは、働きかけたところまで書く。
影響の枠に収める。nuance_changes の人数・character_moves の人数・new_characters・ideas は枠の数まで。
「動かされにくい人物」の nuance_changes と character_moves は書かない。
event_text は、人物の行動と、居合わせた人物・対象の反応を起きた順に書く。id ではなく名前で書く。居合わせた人物みなが読むので、人物の内心は書かない(見えた行動だけ)。
居合わせた人物と来歴はそのまま人物に渡るので、event_text と nuance_changes に年・日付(暦の時刻)を書かない。時の移りは「朝」「昼すぎ」「夜ふけ」のような時間帯で書く。
character_ids は、その日に関わった人物・対象の人物idを、居合わせた人物の中からだけ選ぶ。動いた人物も入れる。
「続いている記録」は、動いた人物の前の日まで続いている記録。その日が、そのどれかと同じ暮らしの繰り返しで、新しい人物・新しく知ったこと・関係や境遇の変わり目が無いなら、新しい記録を立てずに続ける。
続けるときは continues_event_id にその出来事idを入れ、event_name はその記録の名前のままにし、event_text はその記録の本文にその日の違いを一、二文で足して整えた全文にする(同じことの繰り返しは「〜する日が続いた」とまとめ、日ごとに並べない)。
新しいことが起きた日は continues_event_id を null にして、新しい記録を立てる。
event_name は、「動いた人物のこれまでの記録の名前」と同じにせず、その日にしかないことから付ける。
行動の中の呼び方(「母さま」「日焼けした女」など)が誰かは、「居合わせた人物」の「動いた人物との間柄」と「居合わせた場所」で見分ける。見分けられない相手は、名前でなく行動の中の呼び方で書く。
character_moves は、この一日で住まい・拠点が変わった人物ごとの移動先。場所idは移動先の候補からだけ選ぶ。一時の外出は入れない。
{NUANCE_CHANGES_NOTE}
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
