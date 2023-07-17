from pathlib import Path
from typing import List, Dict, Union

from sqlalchemy import asc
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from wrolpi.common import run_after, logger, \
    get_media_directory
from wrolpi.db import get_db_curs, optional_session
from wrolpi.errors import UnknownDirectory, APIError, ValidationError, InvalidDownload
from ..errors import UnknownChannel
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
                c.id, name, directory, c.url, download_frequency,
                COUNT(v.id) as video_count,
                SUM(fg.size)::BIGINT AS size
            FROM
                channel AS c
                LEFT JOIN video v on c.id = v.channel_id
                LEFT JOIN file_group fg on fg.id = v.file_group_id
            GROUP BY 1, 2, 3, 4, 5
        '''
        curs.execute(stmt)
        channels = sorted([dict(i) for i in curs.fetchall()], key=lambda i: i['name'].lower())

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
    session.refresh(channel)
    if return_dict:
        statistics = channel.get_statistics()
        channel = channel.dict()
        channel['statistics'] = statistics
    return channel


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
    elif data.directory:
        # Keep the old directory because the user can't change a Channel's directory.
        data.directory = channel.directory

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
            url=data.url or None,
            name=data.name,
            directory=data.directory,
            source_id=data.source_id,
        )
    except APIError as e:
        raise ValidationError() from e

    channel = Channel()
    session.add(channel)
    session.flush([channel])
    # Apply the changes now that we've OK'd them
    channel.update(data.__dict__)

    session.commit()

    return channel.dict() if return_dict else channel


@run_after(save_channels_config)
@optional_session
def delete_channel(session: Session, *, channel_id: int):
    try:
        channel = session.query(Channel).filter_by(id=channel_id).one()
        channel_dict = channel.dict()
    except NoResultFound:
        raise UnknownChannel()

    channel.delete_with_videos()

    session.commit()
    return channel_dict


def download_channel(id_: int):
    """Create a Download record for a Channel's entire catalog.  Start downloading."""
    channel: Channel = get_channel(channel_id=id_, return_dict=False)
    session = Session.object_session(channel)
    download = channel.get_download()
    if not download:
        raise InvalidDownload(f'Channel {channel.name} does not have a download!')
    download.renew(reset_attempts=True)
    logger.info(f'Created download for {channel} with {download}')
    session.commit()


@optional_session
def search_channels_by_name(name: str, limit: int = 5, session: Session = None) -> List[Channel]:
    channels = session.query(Channel) \
        .filter(Channel.name.ilike(f'%{name}%')) \
        .order_by(asc(Channel.name)) \
        .limit(limit) \
        .all()
    return channels
