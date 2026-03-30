"""Drop map_subscription table.

Map subscriptions are now managed via settings.regions on a single Download record.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-03-31

"""
from alembic import op

revision = 'c4d5e6f7a8b9'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('DROP TABLE IF EXISTS map_subscription')


def downgrade():
    op.execute('''CREATE TABLE map_subscription (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        region TEXT NOT NULL,
        download_id INTEGER NOT NULL REFERENCES download(id) ON DELETE CASCADE
    )''')
