from pydantic import Field

from data_access_logic.material import Form, Timestamp


class TurnRequest(Form):
    """語り部が足す手番の要求。"""

    character_id: int
    # この手番の作中の時刻
    time: Timestamp | None = None
    # その人物にだけ見える・聞こえるようになったことと、この手番で求めること。何人もに見える状況は語り(`AddTurns` の `narration`)に書く
    request: str = Field(min_length=1)
    # この一手を見聞きする人物。空なら `AddTurns` の `witness_ids`。動く人物自身は入れなくてよい
    witness_ids: list[int] | None = None


class TurnAnswer(Form):
    """人物役が入れる一手。"""

    thought: str | None = None
    # 動かないときも「なし」などと書く(空のままだと、まだ動いていない扱いになる)
    action: str = Field(min_length=1)
    speech: str | None = None
    aim: str | None = None
