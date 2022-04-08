from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import List, Dict, Union, Generator

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from wrolpi.common import run_after, logger, \
    get_media_directory
from wrolpi.dates import today
from wrolpi.db import get_db_curs, optional_session
from wrolpi.downloader import download_manager
from wrolpi.errors import UnknownChannel, UnknownDirectory, APIError, ValidationError, InvalidDownload
from .. import schema
from ..common import check_for_channel_conflicts
from ..lib import save_channels_config
from ..models import Channel

logger = logger.getChild(__name__)


async def get_minimal_channels() -> List[dict]:
    """
    Get the minimum amount of information necessary about all channels.
    """
    with get_db_curs() as curs:
        # Get all channels, even if they don't have videos.
        stmt = '''
            SELECT
                c.id, name, directory, url, download_frequency, info_date,
                (select next_download from download d where d.url=c.url) AS next_download
            FROM
                channel AS c
            ORDER BY LOWER(name)
        '''
        curs.execute(stmt)
        channels = list(map(dict, curs.fetchall()))

    video_counts = await get_channels_video_count()

    for channel in channels:
        channel_id = channel['id']
        channel['video_count'] = video_counts[channel_id]

    return channels


async def get_channels_video_count() -> Dict[int, int]:
    """
    Add video counts to all channels
    """
    with get_db_curs() as curs:
        stmt = 'SELECT id FROM channel'
        curs.execute(stmt)
        # Get all channel IDs, start them with a count of 0.
        video_counts = {int(i['id']): 0 for i in curs.fetchall()}

        stmt = '''
            SELECT
                c.id, COUNT(v.id) AS video_count
            FROM
                channel AS c
                LEFT JOIN video AS v ON v.channel_id = c.id
            WHERE
                v.video_path IS NOT NULL
            GROUP BY 1
        '''
        curs.execute(stmt)
        # Replace all the counts of those channels with videos.
        video_counts.update({int(i['id']): int(i['video_count']) for i in curs.fetchall()})
        return video_counts


COD = Union[dict, Channel]


@optional_session
def get_channel(session: Session, *, channel_id: int = None, source_id: str = None, url: str = None,
                directory: str = None, name: str = None, return_dict: bool = True) -> COD:
    """
    Attempt to find a Channel using the provided params.  The params are in order of reliability.

    Raises UnknownChannel if no channel is found.
    """
    channel: COD = None  # noqa
    # Try to find the channel by the most reliable methods first.
    if channel_id:
        channel = session.query(Channel).filter_by(id=channel_id).one_or_none()
    if not channel and source_id:
        channel = session.query(Channel).filter_by(source_id=source_id).one_or_none()
    if not channel and url:
        channel = session.query(Channel).filter_by(url=url).one_or_none()
    if not channel and directory:
        directory = Path(directory)
        if not directory.is_absolute():
            directory = get_media_directory() / directory
        channel = session.query(Channel).filter_by(directory=directory).one_or_none()
    if not channel and name:
        channel = session.query(Channel).filter_by(name=name).one_or_none()

    if not channel:
        raise UnknownChannel(f'No channel matches {channel_id=} {source_id=} {url=} {directory=}')

    logger.debug(f'Found {channel=} using {channel_id=} {source_id=} {url=} {directory=}')
    if return_dict:
        statistics = channel.get_statistics()
        channel = channel.dict()
        channel['statistics'] = statistics
    return channel


def _spread_by_frequency(channels: List[Channel]) -> Generator[Dict, None, None]:
    channels_by_frequency = defaultdict(lambda: [])
    for channel in channels:
        channels_by_frequency[channel.download_frequency].append(channel)

    for frequency, channels in channels_by_frequency.items():
        # The seconds between each download.
        chunk = frequency // len(channels)
        for channel in channels:
            # My position in the channel group.
            index = channels.index(channel)
            # My next download will be distributed by my frequency and my position.
            position = chunk * index
            next_download = today() + timedelta(seconds=frequency + position)
            yield dict(url=channel.url, frequency=frequency, next_download=next_download)


@run_after(save_channels_config)
@optional_session
def update_channel(session: Session, *, data: schema.ChannelPutRequest, channel_id: int) -> Channel:
    """Update a Channel's DB record"""
    try:
        channel: Channel = session.query(Channel).filter_by(id=channel_id).one()
    except NoResultFound:
        raise UnknownChannel()

    # Only update directory if it was empty
    if data.directory and not channel.directory:
        data.directory = get_media_directory() / data.directory
        if not data.directory.is_dir():
            if data.mkdir:
                data.directory.mkdir()
            else:
                raise UnknownDirectory()

    # Verify that the URL/Name/directory aren't taken
    check_for_channel_conflicts(
        session,
        id_=channel.id,
        url=data.url,
        name=data.name,
        directory=data.directory,
    )

    # Apply the changes now that we've OK'd them
    channel.update(data.__dict__)

    session.commit()

    return channel


@run_after(save_channels_config)
@optional_session
def create_channel(session: Session, data: schema.ChannelPostRequest, return_dict: bool = True) -> Union[Channel, dict]:
    """
    Create a new Channel.  Check for conflicts with existing Channels.
    """
    try:
        # Verify that the URL/Name/directory aren't taken
        check_for_channel_conflicts(
            session,
            url=data.url,
            name=data.name,
            directory=data.directory,
            source_id=data.source_id,
        )
    except APIError as e:
        raise ValidationError() from e

    channel = Channel(
        name=data.name,
        url=data.url,
        match_regex=data.match_regex,
        directory=data.directory,  # noqa
        download_frequency=data.download_frequency,
        source_id=data.source_id,
    )
    session.add(channel)
    session.commit()
    session.flush()
    session.refresh(channel)

    return channel.dict() if return_dict else channel


@run_after(save_channels_config)
@optional_session
def delete_channel(session: Session, *, channel_id: int):
    try:
        channel = session.query(Channel).filter_by(id=channel_id).one()
    except NoResultFound:
        raise UnknownChannel()

    channel.delete_with_videos()

    session.commit()


def download_channel(id_: int):
    """Create a Download record for a Channel's entire catalog.  Start downloading."""
    channel = get_channel(channel_id=id_, return_dict=False)
    session = Session.object_session(channel)
    download = channel.get_download()
    if not download:
        raise InvalidDownload(f'Channel {channel.name} does not have a download!')
    download.renew(reset_attempts=True)
    session.commit()
    download_manager.start_downloads()
