#!/usr/bin/env python3
"""世界の展開を一つ取り消す。展開の中で変えた行(`expansion_change`)を逆の順にたどり、足した行を消し、直した・消した行を
控えた値に戻す。展開のあとで、その行を作者か別の展開が直していたら、何も戻さずに止める(どの行かを返す)。

    RevertExpansion(expansion_id=12).show()
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.expansion.record import RevertedExpansion
from data_access_logic.expansion.rows import model_of
from data_access_logic.query import common_query, expansion_query
from db.guard import restored_value
from db.schema import ChangeOp, Expansion, ExpansionChange, ExpansionStatus
from db.writer import restoring


def _touched_later(s: Session, expansion_id: int) -> list[str]:
    """展開のあとで直された行。行ごとの最後の変更の時刻より、行の直した時刻が新しいもの。"""
    touched = []
    for (table_name, row_id), changed_at in expansion_query.last_change_times(s, expansion_id).items():
        row = s.get(model_of(table_name), row_id)
        if row is not None and row.updated_at > changed_at:
            touched.append(f"{table_name} id={row_id}")
    return touched


def _undo(s: Session, change: ExpansionChange) -> None:
    model = model_of(change.table_name)
    columns = model.__table__.columns
    row = s.get(model, change.row_id)
    if change.op == ChangeOp.ADD:
        if row is not None:
            s.delete(row)
    elif change.op == ChangeOp.UPDATE:
        # 展開のあとで消された行は戻せない(直したことを戻す先が無い)
        if row is not None:
            for key, value in (change.before or {}).items():
                if key != "id":
                    setattr(row, key, restored_value(columns[key], value))
    elif row is None:
        restored = model()
        for key, value in (change.before or {}).items():
            setattr(restored, key, restored_value(columns[key], value))
        s.add(restored)
    # 親子の行は一つずつ書き戻す(親を戻してから子を戻す・子を消してから親を消す順を、記録の逆順のまま守る)
    s.flush()


class RevertExpansion(CommitEntrypoint):
    def __init__(self, expansion_id: int):
        self.expansion_id = expansion_id

    def execute(self, s: Session) -> RevertedExpansion:
        expansion = common_query.get_row(s, Expansion, self.expansion_id)
        if expansion.status == ExpansionStatus.REVERTED:
            raise ValueError(f"expansion id={expansion.id} はもう取り消してある")
        touched = _touched_later(s, expansion.id)
        if touched:
            raise ValueError(f"expansion id={expansion.id} のあとで直された行があるので取り消さない: {', '.join(touched)}")
        changes = s.scalars(expansion_query.changes_select(expansion.id)).all()
        with restoring():
            for change in reversed(changes):
                _undo(s, change)
            expansion.status = ExpansionStatus.REVERTED.value
            s.flush()
        return RevertedExpansion(id=expansion.id, reverted=len(changes))
