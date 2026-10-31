"""A partial index of the unindexed FileGroups.

The modelers and indexers look up `file_group WHERE indexed != 1` (and count it for progress) on every
refresh.  SQLite cannot use an index on `indexed` for `!=`, so each lookup read every file_group row; on a
large library from a cold disk cache that was close to a minute.  This index holds only the unindexed rows.

Revision ID: 2026_10_30_1200
Revises: 2026_10_25_1200
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_10_30_1200'
down_revision = '2026_10_25_1200'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE INDEX IF NOT EXISTS file_group_unindexed_idx ON file_group (id) WHERE "indexed" != 1')


def downgrade():
    op.execute('DROP INDEX IF EXISTS file_group_unindexed_idx')
