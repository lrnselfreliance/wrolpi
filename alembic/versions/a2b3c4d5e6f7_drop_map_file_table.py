"""Drop map_file table.

PMTiles files are now scanned directly from disk; the map_file table is no longer needed.

Revision ID: a2b3c4d5e6f7
Revises: e7f8a9b0c1d2
Create Date: 2026-03-29

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('map_file')


def downgrade():
    op.execute('''CREATE TABLE map_file (
        id SERIAL PRIMARY KEY,
        path TEXT NOT NULL,
        imported BOOLEAN DEFAULT FALSE,
        size BIGINT
    )''')
