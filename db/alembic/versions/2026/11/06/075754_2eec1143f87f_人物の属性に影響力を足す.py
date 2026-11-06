"""人物の属性に影響力を足す

人物モード(`ActCharacter`)で、一手が世界を動かせる幅と、ほかの人物の一手から受ける影響の受けにくさに使う。
性格の列と同じく `personality_level`(無/低/並/高/必)の id を持つ。空なら「並」として読む。

Revision ID: 2eec1143f87f
Revises: f3607015c479
Create Date: 2026-11-06 07:57:54.595079

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2eec1143f87f'
down_revision: Union[str, Sequence[str], None] = 'f3607015c479'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_NAME = "fk_character_parameter_influence_personality_level"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('character_parameter', sa.Column(
        'influence', sa.Integer(), nullable=True,
        comment='影響力。町・組織での立場の重さ。人物モードで、一手が世界を動かせる幅と、ほかの人物の一手から受ける影響の受けにくさ'))
    op.create_foreign_key(_FK_NAME, 'character_parameter', 'personality_level', ['influence'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(_FK_NAME, 'character_parameter', type_='foreignkey')
    op.drop_column('character_parameter', 'influence')
