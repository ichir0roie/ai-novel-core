"""話の枠(plot)と本文(episode)を統合し、plot を episode に改名する

Revision ID: c03cab1e5e7c
Revises: c4d8f2a61e93
Create Date: 2026-09-27 22:36:13.017435

GUI ができたことで、枠と本文を別テーブルに分けていた理由(md への書き出し)が無くなったので、
本文(`episode.text`・`letters`・`model`・`effort`)を枠(`plot`)の列として一行にまとめ、
テーブル自体を `plot` から `episode` に改名する。`plot_idea` も `episode_idea` に付け替える。

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c03cab1e5e7c'
down_revision: Union[str, Sequence[str], None] = 'a4fe8f13c7ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_index(table: str, old: str, new: str, columns: list[str], unique: bool = False) -> None:
    op.drop_index(old, table_name=table)
    op.create_index(new, table, columns, unique=unique)


def upgrade() -> None:
    """Upgrade schema."""
    # 要約(episode_summary.episode_id)は本文行(旧 episode)の id を指していた。
    # 本文行は枠(plot)へ吸収して消すので、対応する枠の id を指すよう先に付け替える
    # (一意索引があるので、いったん負の値へ逃がしてから戻す)
    op.execute(
        "UPDATE episode_summary SET episode_id = -("
        "SELECT episode.plot_id FROM episode WHERE episode.id = episode_summary.episode_id)")
    op.execute("UPDATE episode_summary SET episode_id = -episode_id")

    with op.batch_alter_table('plot', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'text', sa.String(), server_default='', nullable=False, comment='本文。まだ書いていない話(枠だけ)は空文字'))
        batch_op.add_column(sa.Column(
            'letters', sa.Integer(), server_default='0', nullable=False, comment='字数。本文から数える'))
        batch_op.add_column(sa.Column(
            'model', sa.String(), nullable=True, comment='本文を書いたモデル。空なら不明(手で書いた本文など)'))
        batch_op.add_column(sa.Column(
            'effort', sa.String(), nullable=True, comment='本文を書いたときの effort。空なら不明(手で書いた本文など)'))

    op.execute(
        "UPDATE plot SET "
        "text = (SELECT episode.text FROM episode WHERE episode.plot_id = plot.id), "
        "letters = (SELECT episode.letters FROM episode WHERE episode.plot_id = plot.id), "
        "model = (SELECT episode.model FROM episode WHERE episode.plot_id = plot.id), "
        "effort = (SELECT episode.effort FROM episode WHERE episode.plot_id = plot.id) "
        "WHERE EXISTS (SELECT 1 FROM episode WHERE episode.plot_id = plot.id)")

    op.drop_table('episode')

    with op.batch_alter_table('plot_idea', schema=None) as batch_op:
        batch_op.alter_column('plot_id', new_column_name='episode_id', existing_type=sa.Integer(),
                              existing_nullable=False)
    _rename_index('plot_idea', 'ix_plot_idea_plot_id', 'ix_plot_idea_episode_id', ['episode_id'])

    op.rename_table('plot_idea', 'episode_idea')
    _rename_index('episode_idea', 'ix_plot_idea_episode_id', 'ix_episode_idea_episode_id', ['episode_id'])
    _rename_index('episode_idea', 'ix_plot_idea_idea_id', 'ix_episode_idea_idea_id', ['idea_id'])

    op.rename_table('plot', 'episode')


def downgrade() -> None:
    """Downgrade schema."""
    op.rename_table('episode', 'plot')

    _rename_index('episode_idea', 'ix_episode_idea_idea_id', 'ix_plot_idea_idea_id', ['idea_id'])
    _rename_index('episode_idea', 'ix_episode_idea_episode_id', 'ix_plot_idea_episode_id', ['episode_id'])
    op.rename_table('episode_idea', 'plot_idea')

    _rename_index('plot_idea', 'ix_plot_idea_episode_id', 'ix_plot_idea_plot_id', ['plot_id'])
    with op.batch_alter_table('plot_idea', schema=None) as batch_op:
        batch_op.alter_column('episode_id', new_column_name='plot_id', existing_type=sa.Integer(),
                              existing_nullable=False)

    op.create_table(
        'episode',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plot_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('letters', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(), nullable=True),
        sa.Column('effort', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['plot_id'], ['plot.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_episode_plot_id', 'episode', ['plot_id'], unique=True)

    op.execute(
        "INSERT INTO episode (plot_id, text, letters, model, effort) "
        "SELECT id, text, letters, model, effort FROM plot WHERE text != ''")

    with op.batch_alter_table('plot', schema=None) as batch_op:
        batch_op.drop_column('effort')
        batch_op.drop_column('model')
        batch_op.drop_column('letters')
        batch_op.drop_column('text')

    op.execute(
        "UPDATE episode_summary SET episode_id = -("
        "SELECT episode.id FROM episode WHERE episode.plot_id = episode_summary.episode_id)")
    op.execute("UPDATE episode_summary SET episode_id = -episode_id")
