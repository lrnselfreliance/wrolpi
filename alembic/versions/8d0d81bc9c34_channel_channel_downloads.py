"""Channel.downloads / Download.channel

Revision ID: 8d0d81bc9c34
Revises: 00f11f309c53
Create Date: 2024-06-25 22:13:23.885687

"""
import os
import pathlib

from alembic import op
from sqlalchemy import Column, Integer, String, Boolean, JSON, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, deferred

from modules.videos.lib import link_channel_and_downloads
from wrolpi.common import ModelHelper
from wrolpi.media_path import MediaPathType

# revision identifiers, used by Alembic.
revision = '8d0d81bc9c34'
down_revision = '00f11f309c53'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False

Base = declarative_base()


# The `Channel` model at the time of this migration.
class MChannel(ModelHelper, Base):
    __tablename__ = 'channel'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    url = Column(String, unique=True)
    directory: pathlib.Path = Column(MediaPathType)
    generate_posters = Column(Boolean, default=False)
    calculate_duration = Column(Boolean, default=True)
    source_id = Column(String)
    refreshed = Column(Boolean, default=False)

    info_json = deferred(Column(JSON))
    info_date = Column(Date)

    @staticmethod
    def get_by_url(url: str, session: Session = None):
        if not url:
            raise RuntimeError('Must provide URL to get Channel')
        channel = session.query(MChannel).filter_by(url=url).one_or_none()
        return channel

    def get_rss_url(self) -> str | None:
        if self.url and self.source_id and 'youtube.com' in self.url:
            return f'https://www.youtube.com/feeds/videos.xml?channel_id={self.source_id}'


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE download ADD CONSTRAINT download_url_unique UNIQUE (url)')
    session.execute('ALTER TABLE download ADD COLUMN channel_id INTEGER REFERENCES channel(id)')

    link_channel_and_downloads(session, MChannel)

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
