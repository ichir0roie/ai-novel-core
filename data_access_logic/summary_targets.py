"""材料に要約で渡す話・出来事。AI に渡す前に、要約を本文に揃えておく。

材料を組む関数(`*_material`)は要約をそのまま読むだけで作り直さないので、先に `*_targets` で対象を引いて揃える。
揃えるのは流れ(`data_access_logic/flows/summary.py`)
(古い要約の元を一度に引き、AI の結果は得たその場で一件ずつ書き戻して commit する)。
"""
import logging


from data_access_logic.material import Material

logger = logging.getLogger(__name__)


class SummaryTargets(Material):
    episode_ids: list[int] = []
    event_ids: list[int] = []
