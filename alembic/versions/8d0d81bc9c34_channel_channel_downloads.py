"""Channel.channel_downloads

Revision ID: 8d0d81bc9c34
Revises: 00f11f309c53
Create Date: 2024-06-25 22:13:23.885687

"""
import os

from alembic import op
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '8d0d81bc9c34'
down_revision = '00f11f309c53'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False

Base = declarative_base()


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE download ADD CONSTRAINT download_url_unique UNIQUE (url)')
    session.execute('''
    CREATE TABLE channel_download (
        channel_id INTEGER REFERENCES channel (id),
        download_url TEXT REFERENCES download (url),
        primary key (channel_id, download_url)
    )''')

    # Migration is separated for testing.  See `test_channel_channel_downloads_migration`
    from wrolpi.migration import migrate_channel_downloads
    migrate_channel_downloads(session)

    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS match_regex')
    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS download_frequency')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.channel_download OWNER TO wrolpi')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP TABLE IF EXISTS channel_download')
    session.execute('ALTER TABLE channel ADD COLUMN IF NOT EXISTS match_regex TEXT')
    session.execute('ALTER TABLE channel ADD COLUMN IF NOT EXISTS download_frequency INTEGER')
    session.execute('ALTER TABLE download DROP CONSTRAINT IF EXISTS download_url_unique')
