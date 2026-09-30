"""ルーチンの生存確認 ai_worker と、ai_task の worker_id・fired_at を消す

Revision ID: 376993ccf815
Revises: 70f7710679d8
Create Date: 2026-09-30 21:01:48.326761

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '376993ccf815'
down_revision: Union[str, Sequence[str], None] = '70f7710679d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # worker_id の FK(名前が無い)は列と一緒に消える。ai_worker を指す FK が無くなってから表を消す
    with op.batch_alter_table('ai_task', schema=None) as batch_op:
        batch_op.drop_column('fired_at')
        batch_op.drop_column('worker_id')
        batch_op.alter_column(
            'attempts', existing_type=sa.Integer(), existing_nullable=False, existing_server_default='0',
            comment='拾った回数。回したセッションが途中で止まって拾い直すたびに増え、上限を超えたら failed にする',
            existing_comment='拾った回数。ルーチンが途中で止まって拾い直すたびに増え、上限を超えたら failed にする')
    op.drop_table('ai_worker')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('ai_worker',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('session', sa.VARCHAR(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('heartbeat_at', sa.DateTime(), nullable=False),
    sa.Column('stopped_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_task', schema=None) as batch_op:
        batch_op.alter_column(
            'attempts', existing_type=sa.Integer(), existing_nullable=False, existing_server_default='0',
            comment='拾った回数。ルーチンが途中で止まって拾い直すたびに増え、上限を超えたら failed にする',
            existing_comment='拾った回数。回したセッションが途中で止まって拾い直すたびに増え、上限を超えたら failed にする')
        batch_op.add_column(sa.Column('worker_id', sa.INTEGER(), nullable=True))
        batch_op.add_column(sa.Column('fired_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key('fk_ai_task_worker_id_ai_worker', 'ai_worker', ['worker_id'], ['id'])
