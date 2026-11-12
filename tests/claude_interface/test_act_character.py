"""人物モード(`ActCharacter`)。人物の一手と、巻きこんだ相手との対話、まとめて裁いた結果を足すこと(足すことと end を入れることだけ)と、
気力・手数・影響の枠による縛り。"""
import json

from sqlalchemy import select

from data_access_logic import constants
from data_access_logic.character.record import CharacterMove, MotivationChange
from data_access_logic.event.progress_models import CharacterUpdateDraft
from data_access_logic.expansion import budget
from data_access_logic.expansion.act_character import ActCharacter
from data_access_logic.expansion.act_models import (
    ActIdeaDraft, ActOutcomeDraft, BatchOutcomeDraft, BatchOutcomeItem, DialogueTurnDraft, ImpactFrame, IntentDraft,
    InviteDraft, NarrationDraft, NewCharacterDraft,
)
from data_access_logic.expansion.read_expansion import ReadExpansion
from data_access_logic.expansion.revert_expansion import RevertExpansion
from data_access_logic.flows import act
from db.schema import (
    Character, CharacterHistory, CharacterLocation, CharacterMotivation, CharacterParameter, CharacterRelation, Episode,
    EpisodeCharacter, Event, EventCharacter, Expansion, IdeaHistory, get_env_session,
)
from db.stamp import Stamp
from tool.test.mock_ai_client import MockAIClient


def _outcome(actor_id: int, destination_id: int, arc_closed: bool, others: list[int],
             motivation_changes: list[MotivationChange] | None = None) -> dict:
    return dict(
        event_name="診療所の開業", event_text="村の空き家を借りて診療所を開いた", character_ids=[actor_id, *others],
        character_moves=[CharacterMove(character_id=id_, location_id=destination_id) for id_ in [actor_id, *others]],
        character_updates=[CharacterUpdateDraft(character_id=id_, text="【名前】は手を貸すと決めた") for id_ in others],
        location_abolished=False, location_founded=None, event_duration_days=3,
        ideas=[ActIdeaDraft(keyword="潮風療法", kind="技術", description="潮風に当てて熱を下げる手当て",
                            called="潮風の手当て", detail="熱が下がると村人は信じている", knower_ids=[actor_id])],
        new_characters=[NewCharacterDraft(description="診療所で雇われた若い助手", person=True, relation="雇い人")],
        motivation_changes=motivation_changes or [], arc_closed=arc_closed)


class ScriptedAI(MockAIClient):
    """人物の一手・対話の手番・まとめた裁きだけを決めた答えにする。人物の生成などほかの呼び出しはモックに任せる。"""

    def __init__(self, actor_id: int, destination_id: int, arc_id: int | None = None, arc_closed: bool = False,
                 invite_ids: list[int] | None = None, motivation_id: int | None = None,
                 motivation_changes: list[MotivationChange] | None = None):
        super().__init__(seed=0)
        self.actor_id = actor_id
        self.destination_id = destination_id
        self.arc_id = arc_id
        self.arc_closed = arc_closed
        self.invite_ids = invite_ids or []
        self.motivation_id = motivation_id
        self.motivation_changes = motivation_changes

    def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
        call = {"output": output, "prompt": prompt, "system": system, "style_scope": style_scope, "model": model,
                "effort": effort}
        if output is IntentDraft:
            self.calls.append(call)
            return IntentDraft(inner="港の病人を放っておけない", aim="村に診療所を開く", action="村へ移って診療所を開く",
                               speech="ここで診ます", motivation_id=self.motivation_id, arc_id=self.arc_id,
                               new_arc_name=None if self.arc_id is not None else "診療所を開く",
                               invites=[InviteDraft(character_id=id_, reason="手伝ってほしい") for id_ in self.invite_ids])
        if output is DialogueTurnDraft:
            self.calls.append(call)
            if "あなたはこの狙いで動いている" in prompt:
                return DialogueTurnDraft(thought="これで決まり", action="頭を下げる", speech="助かる", aim="礼を言う", done=True)
            return DialogueTurnDraft(thought="放っておけない", action="うなずく", speech="手を貸す", aim="手伝う", done=False)
        if output is NarrationDraft:
            self.calls.append(call)
            return NarrationDraft(motivation="診療所の話より前に村へ移らせない", narration="港から使いが来て、病人が増えたと告げた",
                                  request="使いの話を聞く")
        if output is BatchOutcomeDraft:
            self.calls.append(call)
            acts = json.loads(prompt.rsplit("\n", 1)[0])["手"]
            return BatchOutcomeDraft(outcomes=[
                BatchOutcomeItem(act_number=item["手の番号"],
                                 **_outcome(self.actor_id, self.destination_id, self.arc_closed, self.invite_ids,
                                            self.motivation_changes))
                for item in acts])
        return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                effort=effort, style_scope=style_scope)

    def calls_of(self, output) -> list[dict]:
        return [call for call in self.calls if call.get("output") is output]


def _one(run):
    assert not run.failed, run.failed
    assert len(run.acted) == 1
    return run.acted[0]


def test_act_character_adds_rows_and_records_the_expansion(world):
    actor_id = world.character_ids[1]
    ai = ScriptedAI(actor_id, world.neighbor_id)

    acted = _one(act.act_character(character_id=actor_id, time="1200/05/01", seed=1, ai=ai))

    assert acted.actor.character_id == actor_id and acted.actor.location_id == world.location_id
    assert acted.arc_id is not None and acted.event.name == "診療所の開業"
    # 人物の目には、作者だけが読む筋書きを渡さない
    intent_call = ai.calls_of(IntentDraft)[0]
    assert "あなたが知っていること" in intent_call["prompt"]
    # 人物の目の段は一番安いモデル、裁く段は強いモデル
    assert (intent_call["model"], intent_call["effort"]) == (constants.ACT_MODEL, constants.ACT_EFFORT)
    judge_call = ai.calls_of(BatchOutcomeDraft)[0]
    assert (judge_call["model"], judge_call["effort"]) == (constants.ACT_JUDGE_MODEL, constants.ACT_JUDGE_EFFORT)
    with get_env_session() as s:
        expansion = s.get_one(Expansion, acted.expansion_id)
        assert (expansion.mode, expansion.status, expansion.actor_id) == ("character", "done", actor_id)
        assert "村に診療所を開く" in expansion.prompt
        event = s.get_one(Event, acted.event.id)
        arc = s.get_one(Event, acted.arc_id)
        assert (event.origin, event.parent_event_id, arc.end) == ("ai", arc.id, None)
        rows = s.scalars(select(CharacterLocation).where(CharacterLocation.character_id == actor_id)
                         .order_by(CharacterLocation.id)).all()
        assert rows[0].end == Stamp.parse("1200/05/01") and rows[0].origin == "user"
        assert (rows[-1].location_id, rows[-1].origin) == (world.neighbor_id, "ai")
        called = s.scalars(select(IdeaHistory).where(IdeaHistory.name == "潮風の手当て")
                           .order_by(IdeaHistory.id.desc())).first()
        assert called is not None and [knower.knower_id for knower in called.knowers] == [actor_id]
        assert s.get_one(Character, actor_id).origin == "user"
    detail = ReadExpansion(expansion_id=acted.expansion_id).run()
    assert isinstance(detail, dict)
    assert {change["op"] for change in detail["changes"]} <= {"add", "update"}


def test_act_character_continues_and_closes_an_arc(world):
    actor_id = world.character_ids[1]
    first = _one(act.act_character(character_id=actor_id, time="1200/05/01", seed=1,
                                   ai=ScriptedAI(actor_id, world.neighbor_id)))
    second = _one(act.act_character(character_id=actor_id, time="1200/06/01", seed=2,
                                    ai=ScriptedAI(actor_id, world.location_id, arc_id=first.arc_id, arc_closed=True)))

    assert second.arc_id == first.arc_id
    with get_env_session() as s:
        assert s.get_one(Event, first.arc_id).end == Stamp.parse("1200/06/01")
        assert s.get_one(Event, second.event.id).parent_event_id == first.arc_id


def test_act_character_can_be_reverted(world):
    actor_id = world.character_ids[1]
    with get_env_session() as s:
        histories_before = len(s.get_one(Character, actor_id).histories)
    acted = _one(act.act_character(character_id=actor_id, time="1200/05/01", seed=1,
                                   ai=ScriptedAI(actor_id, world.neighbor_id)))

    RevertExpansion(expansion_id=acted.expansion_id).run()

    with get_env_session() as s:
        assert s.get(Event, acted.event.id) is None
        rows = s.scalars(select(CharacterLocation).where(CharacterLocation.character_id == actor_id)).all()
        assert [row.end for row in rows] == [None]
        assert len(s.scalars(select(CharacterHistory).where(CharacterHistory.character_id == actor_id)).all()) \
            == histories_before


def test_act_character_picks_a_sub_character(world):
    actor_id = world.character_ids[1]
    run = act.act_character(time="1200/05/01", seed=3, ai=ScriptedAI(actor_id, world.neighbor_id))
    with get_env_session() as s:
        assert s.get_one(Character, _one(run).actor.character_id).main_character is False


def test_act_character_entrance_is_registered():
    from gui.api import interface

    assert interface.entrance_class("expansion.act_character.ActCharacter") is ActCharacter


def test_failed_act_marks_the_expansion_failed(world):
    class Silent(MockAIClient):
        def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
            return None

    run = act.act_character(character_id=world.character_ids[1], time="1200/05/01", ai=Silent())

    assert not run.acted and "一手が得られなかった" in run.failed[0].error
    with get_env_session() as s:
        assert s.get_one(Expansion, run.failed[0].expansion_id).status == "failed"


def test_invited_character_talks_and_a_stronger_one_is_not_moved(world):
    """花子(影響力 並)が主要人物の太郎(影響力は高として扱う)を巻きこむ。太郎は手番で応じるが、
    花子の一手では太郎の人となりの変化・住まいの移動は書かれない。"""
    actor_id, main_id = world.character_ids[1], world.character_ids[0]
    ai = ScriptedAI(actor_id, world.neighbor_id, invite_ids=[main_id])

    acted = _one(act.act_character(character_id=actor_id, time="1200/05/01", seed=1, ai=ai))

    assert acted.invited_ids == [main_id]
    assert [turn.character_id for turn in acted.dialogue] == [actor_id, main_id, actor_id]
    turn_calls = ai.calls_of(DialogueTurnDraft)
    assert {call["model"] for call in turn_calls} == {constants.ACT_MODEL}
    # 巻きこまれた太郎は、花子の口火を名前つきで見聞きしている(幼なじみなので名前を知っている)
    assert "テスト花子: 村へ移って診療所を開く「ここで診ます」" in turn_calls[0]["prompt"]
    assert acted.frame is not None and acted.frame.resistant_ids == [main_id]
    with get_env_session() as s:
        expansion = s.get_one(Expansion, acted.expansion_id)
        assert "巻きこんだ相手とのやり取り" in expansion.prompt and "手を貸す" in expansion.prompt
        locations = s.scalars(select(CharacterLocation).where(CharacterLocation.character_id == main_id)).all()
        assert [row.end for row in locations] == [None]
        assert not [history for history in s.scalars(select(CharacterHistory).where(
            CharacterHistory.character_id == main_id)).all() if history.origin == "ai"]


def test_energy_runs_out_and_recovers(world):
    actor_id = world.character_ids[1]
    _one(act.act_character(character_id=actor_id, time="1200/05/01", seed=1,
                           ai=ScriptedAI(actor_id, world.neighbor_id)))

    # 行動力 低(気力の上限 3)で一手に 2 使うので、翌日にはもう打てない
    tired = act.act_character(character_id=actor_id, time="1200/05/02", seed=2,
                              ai=ScriptedAI(actor_id, world.location_id))
    assert not tired.acted and "気力か手数が足りない" in tired.failed[0].error
    # 時刻を省けば、気力の戻る日まで待ってから動く
    rested = _one(act.act_character(character_id=actor_id, seed=3, ai=ScriptedAI(actor_id, world.location_id)))
    with get_env_session() as s:
        character = s.get_one(Character, actor_id)
        assert budget.energy_at(s, character, Stamp.parse(rested.actor.time)) >= 0


def test_one_judge_call_for_the_whole_run(world):
    actor_id = world.character_ids[1]
    with get_env_session() as s:
        other = Character(name="テスト次郎", text="テスト次郎の説明", kind="人物", main_character=False, end="1260/01/01",
                          parameters=[CharacterParameter(start="1170/01/01", sex="男", proactivity="高")])
        s.add(other)
        s.flush()
        s.add(CharacterLocation(character_id=other.id, location_id=world.location_id, start="1170/01/01"))
        s.add(CharacterRelation(character_1_id=actor_id, character_2_id=other.id, relation="隣人", text="", start="1180/01/01"))
        s.commit()
    ai = ScriptedAI(actor_id, world.neighbor_id)

    run = act.act_character(character_id=actor_id, time="1200/05/01", seed=1, act_count=2, ai=ai)

    assert len(ai.calls_of(BatchOutcomeDraft)) == 1
    assert len(ai.calls_of(IntentDraft)) == len(run.acted) + len(
        [failure for failure in run.failed if failure.expansion_id is not None])
    assert actor_id in [acted.actor.character_id for acted in run.acted]
    # 同じ実行で同じ人物は二度動かない
    assert len({acted.actor.character_id for acted in run.acted}) == len(run.acted)


def _plotted_episode(story_id: int, character_ids: list[int], start: str, plot: str, cast: bool = True) -> int:
    with get_env_session() as s:
        episode = Episode(story_id=story_id, title="テスト港の話", plot_text=plot, start=start)
        s.add(episode)
        s.flush()
        if cast:
            s.add_all([EpisodeCharacter(episode_id=episode.id, character_id=id_) for id_ in character_ids])
        s.commit()
        return episode.id


def test_narrator_takes_the_plot_as_its_motive(world):
    """一手の前後に、動く人物が出るプロットつきの話があれば、語り部がそのプロットを動機にする。
    人物には語りと要求だけが渡り、プロットと動機は裁く段にだけ渡る。"""
    actor_id = world.character_ids[1]
    episode_id = _plotted_episode(world.story_id, [actor_id], "1230/03/05", "港で疫病の噂が立つ。花子は港に残って病人を診る")
    ai = ScriptedAI(actor_id, world.neighbor_id)

    acted = _one(act.act_character(character_id=actor_id, time="1230/03/01", seed=1, ai=ai))

    narrator_call = ai.calls_of(NarrationDraft)[0]
    assert "港に残って病人を診る" in narrator_call["prompt"]
    assert (narrator_call["model"], narrator_call["effort"], narrator_call["style_scope"]) == (
        constants.ACT_NARRATOR_MODEL, constants.ACT_NARRATOR_EFFORT, "語り部")
    intent_prompt = ai.calls_of(IntentDraft)[0]["prompt"]
    assert "港から使いが来て" in intent_prompt and "使いの話を聞く" in intent_prompt
    assert "港に残って病人を診る" not in intent_prompt and "診療所の話より前に" not in intent_prompt
    judge_prompt = ai.calls_of(BatchOutcomeDraft)[0]["prompt"]
    assert "港に残って病人を診る" in judge_prompt and "診療所の話より前に村へ移らせない" in judge_prompt
    assert acted.narration is not None and [episode.id for episode in acted.narration.episodes] == [episode_id]
    with get_env_session() as s:
        prompt = s.get_one(Expansion, acted.expansion_id).prompt
        assert prompt.startswith(f"語り部の動機(ep{episode_id}「テスト港の話」)") and "村に診療所を開く" in prompt


def test_narrator_finds_an_episode_by_a_name_in_the_plot(world):
    actor_id = world.character_ids[1]
    # 前に回したテストの話が同じ名前で残り、近い話の上限を埋めるので、この回だけの名前にする
    name = f"テスト峠越え{actor_id}"
    with get_env_session() as s:
        s.get_one(Character, actor_id).name = name
        s.commit()
    episode_id = _plotted_episode(world.story_id, [], "1231/06/20", f"{name}が峠を越える", cast=False)
    ai = ScriptedAI(actor_id, world.neighbor_id)

    acted = _one(act.act_character(character_id=actor_id, time="1231/06/01", seed=1, ai=ai))

    assert acted.narration is not None and [episode.id for episode in acted.narration.episodes] == [episode_id]


def test_no_narrator_without_a_related_episode(world):
    actor_id = world.character_ids[1]
    # 遠すぎる話と、ほかの人物だけが出る話は関わらない
    _plotted_episode(world.story_id, [actor_id], "1232/12/01", "港で疫病の噂が立つ")
    _plotted_episode(world.story_id, [], "1232/03/02", "名も無い旅人が峠を越える", cast=False)
    ai = ScriptedAI(actor_id, world.neighbor_id)

    acted = _one(act.act_character(character_id=actor_id, time="1232/03/01", seed=1, ai=ai))

    assert not ai.calls_of(NarrationDraft) and acted.narration is None
    assert '"語り部の動機": null' in ai.calls_of(BatchOutcomeDraft)[0]["prompt"]


def test_plots_reach_the_judge_even_if_the_narrator_is_silent(world):
    actor_id = world.character_ids[1]
    _plotted_episode(world.story_id, [actor_id], "1233/03/05", "港に残って病人を診る")

    class SilentNarrator(ScriptedAI):
        def generate(self, prompt, output, system=None, timeout=None, tools=(), model="", effort="", style_scope=None):
            if output is NarrationDraft:
                return None
            return super().generate(prompt, output, system=system, timeout=timeout, tools=tools, model=model,
                                    effort=effort, style_scope=style_scope)

    ai = SilentNarrator(actor_id, world.neighbor_id)
    acted = _one(act.act_character(character_id=actor_id, time="1233/03/01", seed=1, ai=ai))

    assert acted.narration is not None and acted.narration.motivation is None
    assert "港に残って病人を診る" in ai.calls_of(BatchOutcomeDraft)[0]["prompt"]


def test_clamp_keeps_the_actor_first_and_cuts_the_rest():
    changes = [MotivationChange(character_id=id_, motivation_id=None, strength=2, text="思い") for id_ in (3, 2, 1)]
    outcome = ActOutcomeDraft(**_outcome(1, 9, False, [2, 3, 4], changes))
    frame = ImpactFrame(influence="低", people=2, moves=1, new_characters=0, ideas=1, location_change=False,
                        resistant_ids=[3])

    clamped = budget.clamp(outcome, frame, actor_id=1)

    assert [move.character_id for move in clamped.character_moves] == [1]
    assert [update.character_id for update in clamped.character_updates] == [2, 4]
    assert clamped.new_characters == [] and len(clamped.ideas) == 1
    # 動かされにくい人物の思いは書かず、動いた人物の思いを先に残す
    assert [change.character_id for change in clamped.motivation_changes] == [1, 2]


def test_actor_acts_on_motivations_and_the_events_around(world):
    """花子は効いているモチベーションと前後の出来事を読んで動き、裁く段の増減で、果たした思いは終わり、
    強さの変わった思いは前の行を終えて新しい行が足され、新しい思いが生まれる。"""
    actor_id, main_id = world.character_ids[1], world.character_ids[0]
    with get_env_session() as s:
        cure = CharacterMotivation(character_id=actor_id, start="1199/01/01", strength=4, text="港の病人を救いたい")
        calm = CharacterMotivation(character_id=actor_id, start="1199/01/01", strength=2, text="静かに暮らしたい")
        over = CharacterMotivation(character_id=actor_id, start="1198/01/01", end="1199/06/01", strength=3,
                                   text="もう終わった思い")
        future = CharacterMotivation(character_id=actor_id, start="1201/01/01", strength=5, text="まだ生まれていない思い")
        festival = Event(name="テスト村祭り", text="都で祭りが開かれる", time="1200/08/01", start="1200/08/01",
                         location_id=world.location_id, event_characters=[EventCharacter(character_id=actor_id)])
        s.add_all([cure, calm, over, future, festival])
        s.commit()
        cure_id, calm_id, over_id = cure.id, calm.id, over.id
    changes = [
        MotivationChange(character_id=actor_id, motivation_id=cure_id, strength=0, text=None),
        MotivationChange(character_id=actor_id, motivation_id=calm_id, strength=3, text=None),
        MotivationChange(character_id=actor_id, motivation_id=None, strength=3, text="診療所を広めたい"),
        # 効いていない行は指せない
        MotivationChange(character_id=actor_id, motivation_id=over_id, strength=1, text=None),
        # 太郎は花子より影響力が上なので、花子の一手では思いを書かれない
        MotivationChange(character_id=main_id, motivation_id=None, strength=2, text="花子を手伝いたい"),
    ]
    ai = ScriptedAI(actor_id, world.neighbor_id, motivation_id=cure_id, motivation_changes=changes,
                    invite_ids=[main_id])

    acted = _one(act.act_character(character_id=actor_id, time="1200/05/01", seed=1, ai=ai))

    intent_prompt = ai.calls_of(IntentDraft)[0]["prompt"]
    assert intent_prompt.index("港の病人を救いたい") < intent_prompt.index("静かに暮らしたい")
    assert "もう終わった思い" not in intent_prompt and "まだ生まれていない思い" not in intent_prompt
    assert "テスト市" in intent_prompt and "テスト村祭り" in intent_prompt
    # 巻きこまれた太郎は、花子の思いを読まない
    assert "港の病人を救いたい" not in ai.calls_of(DialogueTurnDraft)[0]["prompt"]
    judge_prompt = ai.calls_of(BatchOutcomeDraft)[0]["prompt"]
    assert "居合わせる人物のモチベーション" in judge_prompt and f'"一手が沿ったモチベーションid": {cure_id}' in judge_prompt
    assert sorted(row.text for row in acted.motivations) == ["診療所を広めたい", "静かに暮らしたい"]
    time = Stamp.parse("1200/05/01")
    with get_env_session() as s:
        assert s.get_one(CharacterMotivation, cure_id).end == time
        assert s.get_one(CharacterMotivation, calm_id).end == time
        assert s.get_one(CharacterMotivation, over_id).end == Stamp.parse("1199/06/01")
        added = s.scalars(select(CharacterMotivation).where(
            CharacterMotivation.character_id == actor_id, CharacterMotivation.start == time)).all()
        assert sorted((row.text, row.strength, row.origin) for row in added) == [
            ("診療所を広めたい", 3, "ai"), ("静かに暮らしたい", 3, "ai")]
        assert not s.scalars(select(CharacterMotivation).where(CharacterMotivation.character_id == main_id)).all()

    RevertExpansion(expansion_id=acted.expansion_id).run()

    with get_env_session() as s:
        assert s.get_one(CharacterMotivation, cure_id).end is None
        assert s.get_one(CharacterMotivation, calm_id).end is None
        assert not s.scalars(select(CharacterMotivation).where(
            CharacterMotivation.character_id == actor_id, CharacterMotivation.start == time)).all()
