"""Covering index for browse pages.

The videos/files browse queries filter on mimetype and order by effective_datetime; without a
covering index SQLite scans every file_group row (which carries the indexed texts inline), which
takes ~18 seconds cold on a Pi.  With (mimetype, effective_datetime) the filter, count, and sort
resolve index-only.

Revision ID: 2026_07_14_0900
Revises: 2026_07_10_1350
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_07_14_0900'
down_revision = '2026_07_10_1350'
branch_labels = None
depends_on = None


def upgrade():
    # IF NOT EXISTS: QA boxes may have had the index created manually before this migration.
    op.execute('CREATE INDEX IF NOT EXISTS file_group_mimetype_effective_idx '
               'ON file_group (mimetype, effective_datetime)')


def downgrade():
    op.execute('DROP INDEX IF EXISTS file_group_mimetype_effective_idx')
