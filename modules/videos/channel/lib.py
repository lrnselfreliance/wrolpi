import pathlib
from pathlib import Path
from typing import List, Dict, Union

from sqlalchemy import or_, func, desc, asc
from sqlalchemy.orm import Session

from wrolpi import flags
from wrolpi.common import run_after, logger, \
    get_media_directory, wrol_mode_check
from wrolpi.db import get_db_curs, optional_session, get_db_session
from wrolpi.downloader import save_downloads_config, download_manager
from wrolpi.errors import UnknownDirectory, APIError, ValidationError, RefreshConflict
from .. import schema
from ..common import check_for_channel_conflicts
from ..errors import UnknownChannel, ChannelDirectoryConflict
from ..lib import save_channels_config
from ..models import Channel, Video

logger = logger.getChild(__name__)


async def get_minimal_channels() -> List[dict]:
    """
    Get the minimum amount of information necessary about all channels.
    """
    with get_db_curs() as curs:
        # Get all channels, even if they don't have videos.  Also get the minimum frequency download because this is the
        # one that will consume the most resources.
        stmt = '''
            SELECT
                c.id, c.name AS "name", directory, c.url, t.name AS "tag_name",
                COUNT(v.id) as video_count,
                SUM(fg.size)::BIGINT AS size,
                (
                    select min(d.frequency)
                    from download d
                    where d.channel_id = c.id
                ) AS minimum_frequency
            FROM
                channel AS c
                LEFT JOIN video v on c.id = v.channel_id
                LEFT JOIN file_group fg on fg.id = v.file_group_id
                LEFT JOIN tag t ON t.id = c.tag_id
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
    channel = Channel.find_by_id(channel_id, session)

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
@optional_session(commit=True)
def delete_channel(session: Session, *, channel_id: int):
    channel = Channel.find_by_id(channel_id, session=session)

    channel_dict = channel.dict()
    channel.delete_with_videos()

    return channel_dict


@optional_session
async def search_channels_by_name(name: str, limit: int = 5, session: Session = None,
                                  order_by_video_count: bool = False) -> List[Channel]:
    name = name or ''
    name_no_spaces = ''.join(name.split(' '))
    if order_by_video_count:
        stmt = session.query(Channel, func.count(Video.id).label('video_count')) \
            .filter(or_(
            Channel.name.ilike(f'%{name}%'),
            Channel.name.ilike(f'%{name_no_spaces}%'),
        )) \
            .outerjoin(Video, Video.channel_id == Channel.id) \
            .group_by(Channel.id, Channel.name) \
            .order_by(desc('video_count'), asc(Channel.name)) \
            .limit(limit)
        channels = [i[0] for i in stmt]
    else:
        stmt = session.query(Channel) \
            .filter(or_(
            Channel.name.ilike(f'%{name}%'),
            Channel.name.ilike(f'%{name_no_spaces}%'),
        )) \
            .order_by(asc(Channel.name)) \
            .limit(limit)
        channels = stmt.all()
    return channels


@wrol_mode_check
async def create_channel_download(channel_id: int, url: str, frequency: int, settings: dict):
    """Create Download for Channel."""
    with get_db_session(commit=True) as session:
        channel = Channel.find_by_id(channel_id, session=session)
        download = channel.get_or_create_download(url, frequency, session, reset_attempts=True)
        download.settings = settings

    save_channels_config()
    await save_downloads_config()

    return download


@wrol_mode_check
async def update_channel_download(channel_id: int, download_id: int, url: str, frequency: int, settings: dict):
    """Fetch Channel's Download, update its properties."""
    with get_db_session(commit=True) as session:
        # Ensure that the Channel exists.
        Channel.find_by_id(channel_id, session=session)
        download = download_manager.get_download(session, id_=download_id)
        download.url = url
        download.frequency = frequency
        download.settings = settings
        session.commit()

    download_manager.remove_from_skip_list(url)

    save_channels_config()
    await save_downloads_config()

    return download


@wrol_mode_check
@optional_session
async def tag_channel(tag_name: str, directory: pathlib.Path | None, channel_id: int, session: Session = None):
    """Add a Tag to a Channel, or remove a Tag from a Channel if no `tag_name` is provided.

    Move the Channel to the new directory, if provided."""
    from wrolpi.tags import Tag

    if directory and flags.refreshing.is_set():
        raise RefreshConflict('Refusing to move channel while file refresh is in progress')

    channel = Channel.find_by_id(channel_id, session=session)

    if tag_name:
        tag = Tag.find_by_name(tag_name, session=session)
        channel.tag_id = tag.id
        channel.tag = tag
    else:
        channel.tag = channel.tag_id = None

    session.flush([channel, ])

    # Do not move Channel files into a directory with files.
    if directory and directory.is_dir() and next(directory.iterdir(), None):
        raise ChannelDirectoryConflict('Channel directory already exists and is not empty')

    # Only move Channel when requested.
    if directory:
        # Move to newly defined directory only if necessary.
        logger.info(f'Tagging {channel} with {tag_name} moving to {directory} from {channel.directory}')
        directory.mkdir(parents=True, exist_ok=True)
        if channel.directory != directory:
            await channel.move(directory, session)
    else:
        logger.info(f'Tagging {channel} with {tag_name}')

    session.commit()
