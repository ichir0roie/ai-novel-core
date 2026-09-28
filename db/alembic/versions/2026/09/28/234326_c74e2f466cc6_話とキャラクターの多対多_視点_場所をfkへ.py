"""話とキャラクターの多対多、視点・場所をFKへ

Revision ID: c74e2f466cc6
Revises: c1141ba5ff4e
Create Date: 2026-09-28 23:43:26.227941

話の登場人物を持つ中間テーブル episode_character を足し、自由記述だった
viewpoint(視点)・place(場所)をそれぞれ character.id / location.id への FK にする。
model・effort(本文を書いた AI モデル・エフォート)は列ごと削除する。

既存の viewpoint/place は文字列から一致する行を探して埋める(見つからなければ NULL のまま)。
- viewpoint: 「/」「／」区切りの先頭要素を取り、末尾の丸括弧(半角・全角)を落として character.name
  と完全一致するものを探す。1件だけ当たれば採用
- place: まず location.name と完全一致を探す。無ければ空白(半角・全角)区切りの先頭トークンで
  再度完全一致を探す。1件だけ当たれば採用
"""
from typing import Sequence, Union

import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c74e2f466cc6'
down_revision: Union[str, Sequence[str], None] = 'c1141ba5ff4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_VIEWPOINT_SEP_RE = re.compile(r"[/／]")
_TRAILING_PAREN_RE = re.compile(r"[（(][^（）()]*[）)]\s*\Z")
_WHITESPACE_RE = re.compile(r"[ 　]+")


def _match_viewpoint(viewpoint: str | None, characters: list[tuple[int, str]]) -> int | None:
    if not viewpoint:
        return None
    first = _VIEWPOINT_SEP_RE.split(viewpoint, 1)[0]
    name = _TRAILING_PAREN_RE.sub("", first).strip()
    if not name:
        return None
    matches = [character_id for character_id, character_name in characters if character_name == name]
    return matches[0] if len(matches) == 1 else None


def _match_place(place: str | None, locations: list[tuple[int, str]]) -> int | None:
    if not place:
        return None

    def find(name: str) -> int | None:
        matches = [location_id for location_id, location_name in locations if location_name == name]
        return matches[0] if len(matches) == 1 else None

    exact = find(place)
    if exact is not None:
        return exact
    token = _WHITESPACE_RE.split(place.strip(), 1)[0]
    if token and token != place:
        return find(token)
    return None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.add_column(sa.Column('viewpoint_character_id', sa.Integer(), nullable=True, comment='視点。誰に寄って語るか'))
        batch_op.add_column(sa.Column('place_id', sa.Integer(), nullable=True, comment='場所'))
        batch_op.create_foreign_key('fk_episode_viewpoint_character_id_character', 'character', ['viewpoint_character_id'], ['id'])
        batch_op.create_foreign_key('fk_episode_place_id_location', 'location', ['place_id'], ['id'])

    op.create_table('episode_character',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('episode_id', sa.Integer(), nullable=False),
    sa.Column('character_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['character_id'], ['character.id'], ),
    sa.ForeignKeyConstraint(['episode_id'], ['episode.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('episode_character', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_episode_character_character_id'), ['character_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_episode_character_episode_id'), ['episode_id'], unique=False)

    connection = op.get_bind()
    characters = connection.execute(sa.text("SELECT id, name FROM character")).fetchall()
    locations = connection.execute(sa.text("SELECT id, name FROM location")).fetchall()
    rows = connection.execute(sa.text("SELECT id, viewpoint, place FROM episode")).fetchall()
    for row_id, viewpoint, place in rows:
        viewpoint_character_id = _match_viewpoint(viewpoint, characters)
        place_id = _match_place(place, locations)
        connection.execute(
            sa.text("UPDATE episode SET viewpoint_character_id = :viewpoint_character_id,"
                    " place_id = :place_id WHERE id = :id"),
            {"id": row_id, "viewpoint_character_id": viewpoint_character_id, "place_id": place_id})

    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.drop_column('viewpoint')
        batch_op.drop_column('place')
        batch_op.drop_column('model')
        batch_op.drop_column('effort')


def downgrade() -> None:
    """Downgrade schema。文字列は character.name / location.name から復元する(完全な復元ではない)。"""
    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.add_column(sa.Column('viewpoint', sa.String(), nullable=True, comment='視点。誰に寄って語るか(「ノア(十四歳)」「アウレア / ミレア」)'))
        batch_op.add_column(sa.Column('place', sa.String(), nullable=True, comment='場所。自由記述(「ヴァレンツァ 外れの川」)'))
        batch_op.add_column(sa.Column('model', sa.String(), nullable=True, comment='本文を書いたモデル。空なら不明(手で書いた本文など)'))
        batch_op.add_column(sa.Column('effort', sa.String(), nullable=True, comment='本文を書いたときの effort。空なら不明(手で書いた本文など)'))

    connection = op.get_bind()
    connection.execute(sa.text(
        "UPDATE episode SET viewpoint = ("
        "  SELECT character.name FROM character WHERE character.id = episode.viewpoint_character_id"
        ") WHERE viewpoint_character_id IS NOT NULL"))
    connection.execute(sa.text(
        "UPDATE episode SET place = ("
        "  SELECT location.name FROM location WHERE location.id = episode.place_id"
        ") WHERE place_id IS NOT NULL"))

    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.drop_constraint('fk_episode_place_id_location', type_='foreignkey')
        batch_op.drop_constraint('fk_episode_viewpoint_character_id_character', type_='foreignkey')
        batch_op.drop_column('place_id')
        batch_op.drop_column('viewpoint_character_id')

    with op.batch_alter_table('episode_character', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_episode_character_episode_id'))
        batch_op.drop_index(batch_op.f('ix_episode_character_character_id'))
    op.drop_table('episode_character')
