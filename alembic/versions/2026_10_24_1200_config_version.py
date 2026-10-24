"""Each database config's version, so an import can tell whether the database or the file is newer
(see wrolpi.config_version).

Revision ID: 2026_10_24_1200
Revises: 2026_10_08_1200
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_10_24_1200'
down_revision = '2026_10_08_1200'
branch_labels = None
depends_on = None


def upgrade():
    # No rows: a config's next import (without deletes) records its version.
    op.create_table(
        'config_version',
        sa.Column('name', sa.String(), primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table('config_version')
