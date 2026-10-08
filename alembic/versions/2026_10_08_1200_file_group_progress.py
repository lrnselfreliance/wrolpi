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
    # Not batch_alter_table: rebuilding file_group drops its FTS triggers (see 2026_09_20_1200).
    op.execute('ALTER TABLE file_group DROP COLUMN position')
    op.execute('ALTER TABLE file_group DROP COLUMN progress')
