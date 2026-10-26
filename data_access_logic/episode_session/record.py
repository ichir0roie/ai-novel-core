from data_access_logic.material import Material, Named, Timestamp


class SessionIdeas(Material):
    """語り部が足した語の行き先。本文は返さず、名前だけ(語り部は設定を読まない)。"""

    # 候補のアイデアとして足したものの名前
    added: list[str]
    # 足さなかった語(既にあるアイデアに当たったか、人物・場所の名前)
    kept: list[str]


class KnowerCover(Material):
    """抜けの行と同じ人物・同じ始まりの来歴の行のうち、抜けた登場人物がもう知る相手に入っている行。"""

    history_id: int
    description: str
    # 抜けた登場人物のうち、この行を話の時刻に知っている人物
    knowing: list[Named]


class KnowerGap(Material):
    """登場人物の来歴の行のうち、ほかの登場人物の名前が出るのに、その人物が知る相手に入っていない行。"""

    history_id: int
    character: Named
    start: Timestamp
    description: str
    # 名前が出るが、話の時刻に知らない登場人物
    unknowing: list[Named]
    # 同じ出来事を、知る相手を分けて書いた行がもうあることがある。足す前に読み比べる
    covered_by: list[KnowerCover]
