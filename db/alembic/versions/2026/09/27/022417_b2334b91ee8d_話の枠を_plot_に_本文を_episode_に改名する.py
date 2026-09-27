"""話の枠を plot に、本文を episode に改名する

Revision ID: b2334b91ee8d
Revises: c207213edd7f
Create Date: 2026-09-27 02:24:17.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2334b91ee8d'
down_revision: Union[str, Sequence[str], None] = 'c207213edd7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rebuild_summary(target: str) -> None:
    """episode_summary の episode_id の外部キーを `target` へ向け直す。sqlite は外部キーだけを変えられないので作り直す"""
    op.create_table(
        '_episode_summary_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('episode_id', sa.Integer(), nullable=False),
        sa.Column('source_hash', sa.String(), nullable=False),
        sa.Column('summary', sa.String(), nullable=False),
        sa.Column('style', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['episode_id'], [f'{target}.id']),
        sa.ForeignKeyConstraint(['story_id'], ['story.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute(
        "INSERT INTO _episode_summary_new (id, story_id, episode_id, source_hash, summary, style) "
        "SELECT id, story_id, episode_id, source_hash, summary, style FROM episode_summary")
    op.drop_table('episode_summary')
    op.rename_table('_episode_summary_new', 'episode_summary')
    op.create_index('ix_episode_summary_episode_id', 'episode_summary', ['episode_id'], unique=True)
    op.create_index('ix_episode_summary_story_id', 'episode_summary', ['story_id'])


def _remap_summary(lookup: str) -> None:
    # 一意索引があるので、いったん負の値へ逃がしてから戻す(付け替えの途中で他の行と同じ値にならないように)
    op.execute(f"UPDATE episode_summary SET episode_id = -({lookup})")
    op.execute("UPDATE episode_summary SET episode_id = -episode_id")


def _rename_index(table: str, old: str, new: str, columns: list[str], unique: bool = False) -> None:
    op.drop_index(old, table_name=table)
    op.create_index(new, table, columns, unique=unique)


def _retable_manifest(mapping: dict[str, str]) -> None:
    """md の台帳(`.markdown_sync.json`)が持つ表の名前も合わせる。古いままだと取り込みが md を別の表の行と取り違える"""
    from db.schema import WORLDS_ROOT
    from tool.markdown.sync_manifest import Manifest, locked

    with locked(WORLDS_ROOT):
        manifest = Manifest(WORLDS_ROOT)
        if not manifest.exists:
            return
        for entry in manifest.entries.values():
            entry["table"] = mapping.get(entry["table"], entry["table"])
        manifest.save()


def upgrade() -> None:
    """Upgrade schema."""
    # 要約は本文の要約なので、枠の id から本文の id へ付け替える。本文の無い枠の要約は残さない
    op.execute(
        "DELETE FROM episode_summary WHERE NOT EXISTS "
        "(SELECT 1 FROM episode_text WHERE episode_text.episode_id = episode_summary.episode_id)")
    _remap_summary("SELECT episode_text.id FROM episode_text WHERE episode_text.episode_id = episode_summary.episode_id")
    _rebuild_summary('episode_text')

    # 名前が入れ替わるので、本文を退避名へ逃がしてから枠を plot にする。
    # sqlite は表の改名で他の表の外部キーの参照先も書き換える
    op.rename_table('episode_text', '_episode_body')
    op.rename_table('episode', 'plot')
    op.rename_table('_episode_body', 'episode')
    op.rename_table('episode_idea', 'plot_idea')

    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.alter_column('episode_id', new_column_name='plot_id', existing_type=sa.Integer(),
                              existing_nullable=False)
    _rename_index('episode', 'ix_episode_text_episode_id', 'ix_episode_plot_id', ['plot_id'], unique=True)

    with op.batch_alter_table('plot_idea', schema=None) as batch_op:
        batch_op.alter_column('episode_id', new_column_name='plot_id', existing_type=sa.Integer(),
                              existing_nullable=False)
    _rename_index('plot_idea', 'ix_episode_idea_episode_id', 'ix_plot_idea_plot_id', ['plot_id'])
    _rename_index('plot_idea', 'ix_episode_idea_idea_id', 'ix_plot_idea_idea_id', ['idea_id'])

    _retable_manifest({"episode": "plot", "episode_text": "episode"})


def downgrade() -> None:
    """Downgrade schema."""
    _rename_index('plot_idea', 'ix_plot_idea_idea_id', 'ix_episode_idea_idea_id', ['idea_id'])
    _rename_index('plot_idea', 'ix_plot_idea_plot_id', 'ix_episode_idea_episode_id', ['plot_id'])
    with op.batch_alter_table('plot_idea', schema=None) as batch_op:
        batch_op.alter_column('plot_id', new_column_name='episode_id', existing_type=sa.Integer(),
                              existing_nullable=False)

    _rename_index('episode', 'ix_episode_plot_id', 'ix_episode_text_episode_id', ['plot_id'], unique=True)
    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.alter_column('plot_id', new_column_name='episode_id', existing_type=sa.Integer(),
                              existing_nullable=False)

    op.rename_table('plot_idea', 'episode_idea')
    op.rename_table('episode', '_episode_body')
    op.rename_table('plot', 'episode')
    op.rename_table('_episode_body', 'episode_text')

    _remap_summary("SELECT episode_text.episode_id FROM episode_text WHERE episode_text.id = episode_summary.episode_id")
    _rebuild_summary('episode')

    _retable_manifest({"plot": "episode", "episode": "episode_text"})
