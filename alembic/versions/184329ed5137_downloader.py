"""Downloader

Revision ID: 184329ed5137
Revises: 1870bec7c81e
Create Date: 2021-11-17 19:13:58.305140

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '184329ed5137'
down_revision = '1870bec7c81e'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
        CREATE TABLE download (
            id SERIAL PRIMARY KEY,
            url TEXT NOT NULL,
            status TEXT DEFAULT 'new',
            next_download TIMESTAMPTZ,
            last_successful_download TIMESTAMPTZ,
            frequency INT,
            attempts INT DEFAULT 0
        )
    ''')
    session.execute('ALTER TABLE video ADD COLUMN url TEXT')
    session.execute('ALTER TABLE channel ADD COLUMN source_id TEXT')
    session.execute('CREATE INDEX channel_source_id ON channel (source_id)')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.download OWNER TO wrolpi')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('DROP TABLE IF EXISTS download')
    session.execute('DROP INDEX IF EXISTS channel_source_id')
    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS source_id')
    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS url')
