"""A FileGroup records how far the user is through it: file_group.progress and file_group.position.

Revision ID: 2026_10_08_1200
Revises: 2026_10_06_1500
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_10_08_1200'
down_revision = '2026_10_06_1500'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('file_group', sa.Column('progress', sa.Float(), nullable=True))
    op.add_column('file_group', sa.Column('position', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('file_group') as batch_op:
        batch_op.drop_column('position')
        batch_op.drop_column('progress')
