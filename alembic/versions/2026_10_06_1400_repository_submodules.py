"""A git Repo can also download its submodules: repository.submodules.

Revision ID: 2026_10_06_1400
Revises: 2026_10_06_1300
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_10_06_1400'
down_revision = '2026_10_06_1300'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('repository', sa.Column('submodules', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    with op.batch_alter_table('repository') as batch_op:
        batch_op.drop_column('submodules')
