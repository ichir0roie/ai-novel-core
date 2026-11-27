"""人物の癖と思い込み(`character_nuance`)の入口と、人物役の材料への載り方。"""
import pytest
from pydantic import ValidationError

from data_access_logic.character.commit_character_nuance import CommitCharacterNuance
from data_access_logic.character.delete_character_nuance import DeleteCharacterNuance
from data_access_logic.character.form import CharacterNuanceCreateForm, CharacterNuanceUpdateForm
from data_access_logic.character.list_character_nuances import ListCharacterNuances
from data_access_logic.character.read_knowledge import ReadKnowledge
from data_access_logic.character.update_character_nuance import UpdateCharacterNuance
from db.schema import CharacterNuance, get_env_session


def _commit(**fields) -> dict:
    record = CommitCharacterNuance(CharacterNuanceCreateForm(**fields)).run()
    assert isinstance(record, dict)
    return record


def test_commit_list_update_delete(world):
    character_id = world.character_ids[1]
    habit = _commit(character_id=character_id, situation="止められたとき", text="理由を一つ返して押し通す")
    belief = _commit(character_id=character_id, kind="思い込み", text="人の親切には裏がある", start="1190/01/01")
    ended = _commit(character_id=character_id, situation="褒められたとき", text="黙って目を逸らす", end="1199/01/01")

    assert (habit["kind"], habit["start"], habit["origin"]) == ("癖", None, "user")
    # 時刻を渡せば、その時刻に効いている行を、癖 → 思い込みの順に
    assert [row["id"] for row in ListCharacterNuances(character_id, time="1200/01/01").run()] \
        == [habit["id"], belief["id"]]
    assert [row["id"] for row in ListCharacterNuances(character_id).run()] == [habit["id"], ended["id"], belief["id"]]

    updated = UpdateCharacterNuance(CharacterNuanceUpdateForm(id=habit["id"], text="理由を返して、やってみせる")).run()
    assert isinstance(updated, dict)
    assert (updated["situation"], updated["text"]) == ("止められたとき", "理由を返して、やってみせる")

    DeleteCharacterNuance(character_nuance_id=ended["id"]).run()
    with get_env_session() as s:
        assert s.get(CharacterNuance, ended["id"]) is None


def test_rejects_habit_without_situation_and_belief_with_situation(world):
    character_id = world.character_ids[1]
    with pytest.raises(ValueError, match="場面"):
        _commit(character_id=character_id, text="場面の無い癖")
    with pytest.raises(ValueError, match="場面"):
        _commit(character_id=character_id, kind="思い込み", situation="いつも", text="場面のある思い込み")
    with pytest.raises(ValueError, match="start"):
        _commit(character_id=character_id, situation="朝", text="逆さの期間", start="1200/01/01", end="1199/01/01")
    with pytest.raises(ValidationError):
        CharacterNuanceUpdateForm(id=1, text=None)


def test_knowledge_gives_own_nuances_at_the_time(shown, world):
    taro, hanako = world.character_ids
    _commit(character_id=taro, situation="礼を言われたとき", text="話をそらす")
    _commit(character_id=taro, kind="思い込み", text="ただでくれる物には勘定がついている")
    _commit(character_id=taro, situation="先の話", text="まだ起きていない癖", start="1250/01/01")
    _commit(character_id=hanako, situation="花子の場面", text="花子の癖")

    result = shown(ReadKnowledge(episode_id=world.episode_id, character_id=taro))

    me = result["自分"]
    assert me["癖(場面ごとの振る舞い)"] == [{"場面": "礼を言われたとき", "振る舞い": "話をそらす"}]
    assert me["思い込み"] == ["ただでくれる物には勘定がついている"]
    # ほかの人物の癖は、知っている人物にも渡さない
    assert "花子の癖" not in str(result)


def test_entrances_are_registered():
    from gui.api import interface

    for entrance in ("CommitCharacterNuance", "UpdateCharacterNuance", "DeleteCharacterNuance", "ListCharacterNuances"):
        module = "".join(f"_{c.lower()}" if c.isupper() else c for c in entrance).lstrip("_")
        assert interface.entrance_class(f"character.{module}.{entrance}").__name__ == entrance


def test_apply_nuance_changes_adds_skips_same_and_replaces(world):
    from data_access_logic.character.nuances import apply_nuance_changes, nuances_at
    from data_access_logic.event.progress_models import NuanceChangeDraft
    from db.schema import Character
    from db.stamp import Stamp

    taro, hanako = world.character_ids
    old = _commit(character_id=taro, situation="礼を言われたとき", text="話をそらす", start="1190/01/01")
    time = Stamp.parse("1200/02/01")
    with get_env_session() as s, s.begin():
        people = {id_: s.get_one(Character, id_) for id_ in (taro, hanako)}
        added = apply_nuance_changes(s, [
            # 同じ中身は足さない
            NuanceChangeDraft(character_id=taro, kind="癖", situation="礼を言われたとき", text="話をそらす"),
            # 変わった行は前の行を終えて足す
            NuanceChangeDraft(character_id=taro, kind="癖", situation="礼を言われたとき", text="【名前】は黙ってうなずく",
                              replaces_nuance_id=old["id"]),
            # 相手は居合わせた人物だけ
            NuanceChangeDraft(character_id=hanako, kind="癖", situation="待たされたとき", text="拗ねてみせる",
                              target_character_id=taro),
            NuanceChangeDraft(character_id=hanako, kind="癖", situation="叱られたとき", text="黙る", target_character_id=0),
            # 場面の無い癖と、居合わせない人物の行は捨てる
            NuanceChangeDraft(character_id=hanako, kind="癖", text="場面の無い癖"),
            NuanceChangeDraft(character_id=0, kind="思い込み", text="居合わせない人"),
        ], people, time)
        assert [(row.character_id, row.text, row.target_character_id) for row in added] == [
            (taro, "テスト太郎は黙ってうなずく", None), (hanako, "拗ねてみせる", taro), (hanako, "黙る", None)]
        assert s.get_one(CharacterNuance, old["id"]).end == time
        assert [row.text for row in nuances_at(s, taro, time)] == ["テスト太郎は黙ってうなずく"]
