"""Create map_subscription table.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-03-29

"""
from alembic import op

revision = 'b3c4d5e6f7a8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE map_subscription (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        region TEXT NOT NULL,
        download_id INTEGER NOT NULL REFERENCES download(id) ON DELETE CASCADE
    )''')


def downgrade():
    op.execute('DROP TABLE IF EXISTS map_subscription')
