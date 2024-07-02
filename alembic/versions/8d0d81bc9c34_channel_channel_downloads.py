"""Channel.channel_downloads

Revision ID: 8d0d81bc9c34
Revises: 00f11f309c53
Create Date: 2024-06-25 22:13:23.885687

"""
import os

from alembic import op
from sqlalchemy import Column, Integer, ForeignKey, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '8d0d81bc9c34'
down_revision = '00f11f309c53'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False

Base = declarative_base()


class MDownload(Base):
    __tablename__ = 'download'
    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False, unique=True)


class MChannelDownload(Base):
    __tablename__ = 'channel_download'
    channel_id = Column(Integer, ForeignKey('channel.id'), primary_key=True)
    download_url = Column(String, ForeignKey('download.url'), primary_key=True)


class MChannel(Base):
    __tablename__ = 'channel'
    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True)  # will only be downloaded if ChannelDownload exists.


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

    channels_by_url = {i.url: i for i in session.query(MChannel).all()}
    downloads = session.query(MDownload).all()
    need_commit = False
    for download in downloads:
        channel = channels_by_url.get(download.url)
        if not channel:
            cd = session.query(MChannelDownload).filter_by(download_url=download.url).one_or_none()
            if not cd:
                cd = MChannelDownload(channel_id=channel.id, download_url=download.url)
                session.add(cd)
                need_commit = True

        cd = session.query(MChannelDownload).filter_by(download_url=download.url).one_or_none()
        if not cd:
            cd = MChannelDownload(channel_id=channel.id, download_url=download.url)
            session.add(cd)
            need_commit = True

    channels_by_directory = {i.directory: i for i in session.query(MChannel).all()}
    for download in downloads:
        destination = download.settings.get('destination') if download.settings else None
        if not destination:
            continue

        channel = session.query(MChannel).filter_by(directory=destination).one_or_none()
        if channel:
            pass

    if need_commit:
        session.commit()

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
