"""A git Repo's clone holds a random token: repository.clone_token.

Revision ID: 2026_10_06_1500
Revises: 2026_10_06_1400
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_10_06_1500'
down_revision = '2026_10_06_1400'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('repository', sa.Column('clone_token', sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table('repository') as batch_op:
        batch_op.drop_column('clone_token')
