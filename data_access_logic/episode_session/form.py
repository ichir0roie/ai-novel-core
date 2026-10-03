from pydantic import Field

from data_access_logic.material import Form, Timestamp


class TurnRequest(Form):
    """語り部が足す手番の要求。"""

    character_id: int
    # この手番の作中の時刻
    time: Timestamp | None = None
    # 前の手番から、その人物に見える・聞こえるようになったこと(状況の差分)と、この手番で求めること
    request: str = Field(min_length=1)


class TurnAnswer(Form):
    """人物役が入れる一手。"""

    thought: str | None = None
    # 動かないときも「なし」などと書く(空のままだと、まだ動いていない扱いになる)
    action: str = Field(min_length=1)
    speech: str | None = None
    aim: str | None = None
