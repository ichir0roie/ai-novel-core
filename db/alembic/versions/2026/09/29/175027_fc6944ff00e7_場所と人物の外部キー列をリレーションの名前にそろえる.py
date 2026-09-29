"""場所と人物の外部キー列をリレーションの名前にそろえる

Revision ID: fc6944ff00e7
Revises: c74e2f466cc6
Create Date: 2026-09-29 17:50:27.089413

story.place_id・episode.place_id を location_id に、character_relation.character_id_1・character_id_2 を
character_1_id・character_2_id に名前だけ変える(値はそのまま引き継ぐ)。
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'fc6944ff00e7'
down_revision: Union[str, Sequence[str], None] = 'c74e2f466cc6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('character_relation', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_character_relation_character_id_1'))
        batch_op.drop_index(batch_op.f('ix_character_relation_character_id_2'))
        batch_op.alter_column('character_id_1', new_column_name='character_1_id')
        batch_op.alter_column('character_id_2', new_column_name='character_2_id')

    # 名前を変えた列への index・外部キーは、変えた後の表に張る(同じ batch の中では新しい列名がまだ引けない)
    with op.batch_alter_table('character_relation', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_character_relation_character_1_id'), ['character_1_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_character_relation_character_2_id'), ['character_2_id'], unique=False)

    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.drop_constraint('fk_episode_place_id_location', type_='foreignkey')
        batch_op.alter_column('place_id', new_column_name='location_id')

    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_episode_location_id_location', 'location', ['location_id'], ['id'])

    with op.batch_alter_table('story', schema=None) as batch_op:
        batch_op.alter_column('place_id', new_column_name='location_id')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('story', schema=None) as batch_op:
        batch_op.alter_column('location_id', new_column_name='place_id')

    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.drop_constraint('fk_episode_location_id_location', type_='foreignkey')
        batch_op.alter_column('location_id', new_column_name='place_id')

    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_episode_place_id_location', 'location', ['place_id'], ['id'])

    with op.batch_alter_table('character_relation', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_character_relation_character_1_id'))
        batch_op.drop_index(batch_op.f('ix_character_relation_character_2_id'))
        batch_op.alter_column('character_1_id', new_column_name='character_id_1')
        batch_op.alter_column('character_2_id', new_column_name='character_id_2')

    with op.batch_alter_table('character_relation', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_character_relation_character_id_1'), ['character_id_1'], unique=False)
        batch_op.create_index(batch_op.f('ix_character_relation_character_id_2'), ['character_id_2'], unique=False)
