"""Channel.downloads / Download.channel

Revision ID: 8d0d81bc9c34
Revises: 00f11f309c53
Create Date: 2024-06-25 22:13:23.885687

"""
import os

from alembic import op
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

from modules.videos.lib import link_channel_and_downloads

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
    session.execute('ALTER TABLE download ADD COLUMN channel_id INTEGER REFERENCES channel(id)')

    link_channel_and_downloads(session)

    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS match_regex')
    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS download_frequency')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP TABLE IF EXISTS channel_download')
    session.execute('ALTER TABLE download DROP COLUMN IF EXISTS channel_id')
    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS channel_id')
    session.execute('ALTER TABLE channel ADD COLUMN IF NOT EXISTS match_regex TEXT')
    session.execute('ALTER TABLE channel ADD COLUMN IF NOT EXISTS download_frequency INTEGER')
    session.execute('ALTER TABLE download DROP CONSTRAINT IF EXISTS download_url_unique')
