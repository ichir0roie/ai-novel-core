"""行ごとの暦

暦を作品(`story.custom_stamp_id`)から持ち主の行(話・出来事・人物・アイデア・場所・関係)へ移す。作品の暦は、新しい行の既定として残す。
暦の行に「西暦」(月を持たない行)を足し、暦の無い作品・行は西暦にする。暦は「西暦 + offset」だけで数え、offset が暦の 0 年 1 月 1 日に
なるので、offset より前の時刻を持つ行(子の行も含む)は西暦にする。時点(db の値)は変えない。行の直した時刻(`updated_at`)も進めない。

Revision ID: e6effee9826b
Revises: 7ae96adf5845
Create Date: 2026-11-19 16:42:38.377897

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6effee9826b'
down_revision: Union[str, Sequence[str], None] = '7ae96adf5845'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OWNERS = ("episode", "event", "character", "idea", "location", "character_relation")
_WESTERN = "(SELECT min(id) FROM custom_stamp WHERE name = '西暦')"
# 西暦の 1 年 1 月 1 日 0 時(西暦の行の offset。使わない)
_YEAR_ONE = 10101000000
_STORY_COMMENTS = (("character", "この人物"), ("idea", "このアイデア"), ("location", "この場所"))


def _early(table: str) -> str:
    """持ち主の行(`T`)か、その子の行が、行の暦の offset より前の時刻を持つ。"""
    off = "(SELECT \"offset\" FROM custom_stamp cs WHERE cs.id = T.custom_stamp_id)"

    def own(*columns: str) -> list[str]:
        return [f'T."{column}" < {off}' for column in columns]

    def child(sql: str) -> str:
        return f"EXISTS ({sql})"

    conditions = {
        "episode": own("start", "end"),
        "event": own("time", "end"),
        "character_relation": [
            *own("start", "end"),
            child(f"SELECT 1 FROM character_relation_history h WHERE h.character_relation_id = T.id AND h.start < {off}"),
        ],
        "location": [
            *own("start", "end"),
            child(f"SELECT 1 FROM location_history h WHERE h.location_id = T.id AND h.start < {off}"),
            child("SELECT 1 FROM location_history_knower k JOIN location_history h ON h.id = k.location_history_id "
                  f"WHERE h.location_id = T.id AND k.start < {off}"),
        ],
        "idea": [
            child(f'SELECT 1 FROM idea_history h WHERE h.idea_id = T.id AND (h.start < {off} OR h."end" < {off})'),
            child("SELECT 1 FROM idea_history_knower k JOIN idea_history h ON h.id = k.idea_history_id "
                  f"WHERE h.idea_id = T.id AND k.start < {off}"),
        ],
        "character": [
            *own("end"),
            child(f"SELECT 1 FROM character_parameter p WHERE p.character_id = T.id AND p.start < {off}"),
            child(f'SELECT 1 FROM character_location l WHERE l.character_id = T.id AND (l.start < {off} OR l."end" < {off})'),
            child(f'SELECT 1 FROM character_motivation m WHERE m.character_id = T.id AND (m.start < {off} OR m."end" < {off})'),
            child(f'SELECT 1 FROM character_history h WHERE h.character_id = T.id AND (h.start < {off} OR h."end" < {off})'),
            child("SELECT 1 FROM character_history_knower k JOIN character_history h ON h.id = k.character_history_id "
                  f"WHERE h.character_id = T.id AND k.start < {off}"),
            child("SELECT 1 FROM character_skill_history h JOIN character_skill sk ON sk.id = h.character_skill_id "
                  f'WHERE sk.character_id = T.id AND (h.start < {off} OR h."end" < {off})'),
            child("SELECT 1 FROM character_skill_history_knower k "
                  "JOIN character_skill_history h ON h.id = k.character_skill_history_id "
                  f"JOIN character_skill sk ON sk.id = h.character_skill_id WHERE sk.character_id = T.id AND k.start < {off}"),
        ],
    }
    return " OR ".join(conditions[table])


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("SET LOCAL novel.keep_updated_at = 'on'")

    op.execute(f"INSERT INTO custom_stamp (name, \"offset\") SELECT '西暦', {_YEAR_ONE} "
               "WHERE NOT EXISTS (SELECT 1 FROM custom_stamp WHERE name = '西暦')")
    op.alter_column("custom_stamp", "offset", comment="この暦の 0 年 1 月 1 日 0 時に当たる西暦の時刻(西暦の行では使わない)")

    # 作品の暦は、親の作品からたどった暦を、作品ごとに持つ(新しい行の既定)
    while bind.execute(sa.text(
            "UPDATE story c SET custom_stamp_id = p.custom_stamp_id FROM story p "
            "WHERE c.parent_story_id = p.id AND c.custom_stamp_id IS NULL AND p.custom_stamp_id IS NOT NULL")).rowcount:
        pass
    op.execute(f"UPDATE story SET custom_stamp_id = {_WESTERN} WHERE custom_stamp_id IS NULL")
    op.alter_column("story", "custom_stamp_id", nullable=False,
                    comment="この作品で足す行(話・出来事・人物・アイデア・場所・関係)の暦の既定。行の時刻は行の暦で数える")

    for table, subject in _STORY_COMMENTS:
        op.alter_column(table, "story_id", comment=f"{subject}の属する作品")

    for table in _OWNERS:
        op.add_column(table, sa.Column("custom_stamp_id", sa.Integer(), nullable=True,
                                       comment="この行と子の行の時刻を数える暦"))
        op.create_foreign_key(f"{table}_custom_stamp_id_fkey", table, "custom_stamp",
                              ["custom_stamp_id"], ["id"])
        op.create_index(op.f(f"ix_{table}_custom_stamp_id"), table, ["custom_stamp_id"])

    for table in ("character", "idea", "location", "episode"):
        op.execute(f"UPDATE {table} T SET custom_stamp_id = s.custom_stamp_id FROM story s WHERE T.story_id = s.id")
    op.execute("UPDATE event T SET custom_stamp_id = s.custom_stamp_id FROM story s WHERE T.story_id = s.id")
    op.execute("UPDATE event T SET custom_stamp_id = l.custom_stamp_id FROM location l "
               "WHERE T.custom_stamp_id IS NULL AND T.location_id = l.id")
    op.execute("UPDATE event T SET custom_stamp_id = ("
               "SELECT c.custom_stamp_id FROM event_character ec JOIN character c ON c.id = ec.character_id "
               "WHERE ec.event_id = T.id AND c.custom_stamp_id IS NOT NULL ORDER BY ec.id LIMIT 1) "
               "WHERE T.custom_stamp_id IS NULL")
    op.execute("UPDATE character_relation T SET custom_stamp_id = c.custom_stamp_id FROM character c "
               "WHERE T.character_1_id = c.id")
    for table in _OWNERS:
        op.execute(f"UPDATE {table} SET custom_stamp_id = {_WESTERN} WHERE custom_stamp_id IS NULL")
    # offset より前の時刻を持つ行は、西暦で数える
    for table in _OWNERS:
        op.execute(f"UPDATE {table} T SET custom_stamp_id = {_WESTERN} "
                   f"WHERE T.custom_stamp_id <> {_WESTERN} AND ({_early(table)})")
    for table in _OWNERS:
        op.alter_column(table, "custom_stamp_id", nullable=False)


def downgrade() -> None:
    op.execute("SET LOCAL novel.keep_updated_at = 'on'")
    for table in reversed(_OWNERS):
        op.drop_index(op.f(f"ix_{table}_custom_stamp_id"), table_name=table)
        op.drop_constraint(f"{table}_custom_stamp_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "custom_stamp_id")
    for table, subject in _STORY_COMMENTS:
        op.alter_column(table, "story_id",
                        comment=f"{subject}の属する作品。時刻はこの作品の暦(`Story.custom_stamp_id`)で数える。空なら西暦")
    op.alter_column("story", "custom_stamp_id", nullable=True,
                    comment="この作品と子孫の作品の時刻を数える暦。空なら親の作品の暦、どこにも無ければ西暦")
    op.execute(f"UPDATE story SET custom_stamp_id = NULL WHERE custom_stamp_id = {_WESTERN}")
    op.execute("UPDATE story c SET custom_stamp_id = NULL FROM story p "
               "WHERE c.parent_story_id = p.id AND c.custom_stamp_id = p.custom_stamp_id")
    op.execute("DELETE FROM custom_stamp WHERE name = '西暦'")
    op.alter_column("custom_stamp", "offset",
                    comment="この暦で数え始める西暦の時刻。この時刻の桁は両方の暦で同じで、年の数は西暦から続く")
