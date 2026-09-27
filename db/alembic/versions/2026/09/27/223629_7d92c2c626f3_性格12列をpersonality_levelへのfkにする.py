"""性格12列をpersonality_levelへのFKにする

Revision ID: 7d92c2c626f3
Revises: c4d8f2a61e93
Create Date: 2026-09-27 22:36:29.770542

GUI でプルダウン選択にするため、`character_parameter` の性格12列(誠実性など)を、
無/低/並/高/必の5行だけを持つマスター `personality_level` への FK(Integer)にする。
Python 側は `db.schema.PersonalityLevelType` が id ⇔ 文字列を透過的に変換するので、
呼び出し側(入口・AI 生成)は今までどおり文字列(無/低/並/高/必)のまま扱える。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d92c2c626f3'
down_revision: Union[str, Sequence[str], None] = 'c4d8f2a61e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERSONALITY_COLUMNS = (
    "sincerity", "curiosity", "proactivity", "cooperativeness", "sociability",
    "emotional_expression", "self_esteem", "self_efficacy", "stress_resilience",
    "flexibility_of_values", "sensitivity", "imagination",
)
# personality_level の行の並び(id は 1 始まり)。db/schema.py の PersonalityLevel の宣言順と揃える。
_LEVELS = ("無", "低", "並", "高", "必")


def _fk_name(column: str) -> str:
    return f"fk_character_parameter_{column}_personality_level"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'personality_level',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    personality_level = sa.table(
        'personality_level', sa.column('id', sa.Integer()), sa.column('name', sa.String()))
    op.bulk_insert(
        personality_level, [{'id': index + 1, 'name': name} for index, name in enumerate(_LEVELS)])

    # 文字列(無/低/並/高/必)を、対応するマスター行の id へ寄せてから型を変える
    case_to_id = " ".join(f"WHEN '{name}' THEN {index + 1}" for index, name in enumerate(_LEVELS))
    for column in PERSONALITY_COLUMNS:
        op.execute(f'UPDATE character_parameter SET "{column}" = CASE "{column}" {case_to_id} ELSE NULL END')

    with op.batch_alter_table('character_parameter', schema=None) as batch_op:
        for column in PERSONALITY_COLUMNS:
            batch_op.alter_column(
                column, existing_type=sa.String(), type_=sa.Integer(), existing_nullable=True)
        for column in PERSONALITY_COLUMNS:
            batch_op.create_foreign_key(_fk_name(column), 'personality_level', [column], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('character_parameter', schema=None) as batch_op:
        for column in PERSONALITY_COLUMNS:
            batch_op.drop_constraint(_fk_name(column), type_='foreignkey')
        for column in PERSONALITY_COLUMNS:
            batch_op.alter_column(
                column, existing_type=sa.Integer(), type_=sa.String(), existing_nullable=True)

    case_to_label = " ".join(f"WHEN {index + 1} THEN '{name}'" for index, name in enumerate(_LEVELS))
    for column in PERSONALITY_COLUMNS:
        op.execute(f'UPDATE character_parameter SET "{column}" = CASE "{column}" {case_to_label} ELSE NULL END')

    op.drop_table('personality_level')
