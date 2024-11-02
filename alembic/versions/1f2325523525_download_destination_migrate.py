"""Create `Download.destination` and `Download.tag_names`, migrate from `Download.settings`.

Revision ID: 1f2325523525
Revises: 170d1be52bc7
Create Date: 2024-11-02 11:20:45.028865

"""
import os
from copy import copy

from alembic import op
from sqlalchemy import Column, Integer, Text, String, ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

from wrolpi.common import ModelHelper
from wrolpi.dates import TZDateTime
from wrolpi.downloader import get_download_manager_config, DownloadStatus

# revision identifiers, used by Alembic.
revision = '1f2325523525'
down_revision = '170d1be52bc7'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False

Base = declarative_base()


class MDownload(ModelHelper, Base):
    __tablename__ = 'download'
    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False, unique=True)
    attempts = Column(Integer, default=0)
    destination = Column(Text)
    downloader = Column(Text)
    sub_downloader = Column(Text)
    error = Column(Text)
    frequency = Column(Integer)
    info_json = Column(JSONB)
    last_successful_download = Column(TZDateTime)
    location = Column(Text)
    next_download = Column(TZDateTime)
    settings = Column(JSONB)
    status = Column(String, default=DownloadStatus.new)
    tag_names = Column(ARRAY(Text))


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    for download in session.query(MDownload):
        if not download.settings:
            continue
        # Move `download.settings['destination']` to `download.destination`, if any.
        settings = copy(download.settings) if download.settings else dict()
        destination = settings.pop('destination', None)
        tag_names = settings.pop('tag_names', None)
        if isinstance(excluded_urls := settings.get('excluded_urls'), list):
            settings['excluded_urls'] = ','.join(excluded_urls)
        download.destination = destination or None
        download.tag_names = tag_names or None
        download.settings = settings

    # This will migrate the config as-is at the time that this migration was written.  This code is probably not
    # safe to reuse in the future!

    # Read config file directly.
    try:
        config = get_download_manager_config()
        config._config.update(config.read_config_file())
    except FileNotFoundError:
        # Config does not exist, probably testing, or a new WROLPi.
        return

    new_downloads = []
    for download in session.query(MDownload).order_by(MDownload.url):
        if download.last_successful_download and not download.frequency:
            # This once-download has completed, do not save it.
            continue
        new_download = dict(
            destination=download.destination,
            downloader=download.downloader,
            frequency=download.frequency,
            last_successful_download=download.last_successful_download,
            next_download=download.next_download,
            settings=download.settings,
            status=download.status,
            sub_downloader=download.sub_downloader,
            url=download.url,
        )
        new_downloads.append(new_download)

    # Write directly to file, bypassing usual checks.
    config._config['downloads'] = new_downloads
    config.write_config_data(config._config, config.get_file())


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    for download in session.query(MDownload):
        if download.destination:
            settings = copy(download.settings) if download.settings else dict()
            settings['destination'] = download.destination or settings.get('destination')
            settings['tag_names'] = download.tag_names or settings.get('tag_names')
            if isinstance(excluded_urls := settings.get('excluded_urls'), str):
                settings['excluded_urls'] = excluded_urls.split(',')
            download.settings = settings

    try:
        config = get_download_manager_config()
        config._config.update(config.read_config_file())
    except FileNotFoundError:
        # Config does not exist, probably testing, or a new WROLPi.
        return

    new_downloads = []
    for download in session.query(MDownload).order_by(MDownload.url):
        new_download = dict(
            downloader=download.downloader,
            frequency=download.frequency,
            last_successful_download=download.last_successful_download,
            next_download=download.next_download,
            settings=download.settings,
            status=download.status,
            sub_downloader=download.sub_downloader,
            url=download.url,
        )
        new_downloads.append(new_download)

    config._config['downloads'] = new_downloads
    config.write_config_data(config._config, config.get_file())
