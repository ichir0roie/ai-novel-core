from data_access_logic.material import Material, Named, Timestamp


class TextSaved(Material):
    episode_id: int
    # 保存した本文の字数
    letters: int


class SessionIdeas(Material):
    """語り部が足した語の行き先。本文は返さず、名前だけ(語り部は設定を読まない)。"""

    # 候補のアイデアとして足したものの名前
    added: list[str]
    # 足さなかった語(既にあるアイデアに当たったか、人物・場所の名前)
    kept: list[str]


class KnowerGap(Material):
    """登場人物の来歴の行のうち、ほかの登場人物の名前が出るのに、その人物が知る相手に入っていない行。"""

    history_id: int
    character: Named
    start: Timestamp
    description: str
    # 名前が出るが、話の時刻に知らない登場人物
    unknowing: list[Named]
