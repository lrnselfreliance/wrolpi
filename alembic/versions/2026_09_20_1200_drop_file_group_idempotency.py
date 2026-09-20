"""Drop unused file_group.idempotency.

FileWorker no longer stamps this column (refresh diffs in SQL).  directory.idempotency
is unchanged.  SQLite 3.35+ DROP COLUMN does not rebuild the table, so file_group_fts
(external content on file_group.id) is left intact.

Revision ID: 2026_09_20_1200
Revises: 2026_09_18_1200
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_09_20_1200'
down_revision = '2026_09_18_1200'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE file_group DROP COLUMN idempotency')


def downgrade():
    op.execute('ALTER TABLE file_group ADD COLUMN idempotency DATETIME')
