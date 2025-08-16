import pathlib
from pathlib import Path
from typing import List, Dict, Union

from sqlalchemy import or_, func, desc, asc
from sqlalchemy.orm import Session

from wrolpi import flags
from wrolpi.common import logger, \
    get_media_directory, wrol_mode_check, background_task
from wrolpi.db import get_db_curs, optional_session, get_db_session
from wrolpi.downloader import save_downloads_config, download_manager, Download
from wrolpi.errors import APIError, ValidationError, RefreshConflict
from wrolpi.vars import PYTEST
from .. import schema
from ..common import check_for_channel_conflicts
from ..errors import UnknownChannel
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
               SELECT c.id,
                      c.name AS "name",
                      c.directory,
                      c.url,
                      t.name AS "tag_name",
                      c.video_count,
                      c.total_size,
                      c.minimum_frequency
               FROM channel AS c
                        LEFT JOIN tag t ON t.id = c.tag_id
               '''
        curs.execute(stmt)
        logger.debug(stmt)
        channels = sorted([dict(i) for i in curs.fetchall()], key=lambda i: i['name'].lower())

    return channels


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


@optional_session
async def update_channel(session: Session, *, data: schema.ChannelPutRequest, channel_id: int) -> Channel:
    """Update a Channel's DB record"""
    channel = Channel.find_by_id(channel_id, session)

    # Verify that the URL/Name/directory aren't taken
    check_for_channel_conflicts(
        session,
        id_=channel.id,
        url=data.url,
        name=data.name,
        directory=data.directory,
    )

    data = data.__dict__
    old_directory = pathlib.Path(channel.directory)
    new_directory = get_media_directory() / data.pop('directory')

    # Apply the changes now that we've OK'd them
    channel.update(data)

    session.commit()

    async def _():
        await channel.move_channel(new_directory, session, send_events=True)

    if new_directory != old_directory:
        if not new_directory.is_dir():
            new_directory.mkdir(parents=True)

        if PYTEST:
            await _()
        else:
            background_task(_())

    save_channels_config.activate_switch()

    return channel


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

    directory = pathlib.Path(data.directory)
    directory = get_media_directory() / directory if not directory.is_absolute() else directory
    directory.mkdir(parents=True, exist_ok=True)

    channel = Channel()
    session.add(channel)
    session.flush([channel])
    # Apply the changes now that we've OK'd them
    channel.update(data.__dict__)

    session.commit()

    save_channels_config.activate_switch()

    return channel.dict() if return_dict else channel


@optional_session(commit=True)
def delete_channel(session: Session, *, channel_id: int):
    channel = Channel.find_by_id(channel_id, session=session)

    channel_dict = channel.dict()
    channel.delete_with_videos()

    save_channels_config.activate_switch()

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

    save_channels_config.activate_switch()
    save_downloads_config.activate_switch()

    return download


@wrol_mode_check
async def update_channel_download(channel_id: int, download_id: int, url: str, frequency: int, settings: dict):
    """Fetch Channel's Download, update its properties."""
    with get_db_session(commit=True) as session:
        # Ensure that the Channel exists.
        Channel.find_by_id(channel_id, session=session)
        download = Download.find_by_id(download_id, session=session)
        download.url = url
        download.frequency = frequency
        download.settings = settings
        session.commit()

    download_manager.remove_from_skip_list(url)

    save_channels_config.activate_switch()
    save_downloads_config.activate_switch()

    return download


@wrol_mode_check
@optional_session
async def tag_channel(tag_name: str | None, directory: pathlib.Path | None, channel_id: int, session: Session = None):
    """Add a Tag to a Channel, or remove a Tag from a Channel if no `tag_name` is provided.

    Move the Channel to the new directory, if provided."""

    if directory and flags.refreshing.is_set():
        raise RefreshConflict('Refusing to move channel while file refresh is in progress')

    channel = Channel.find_by_id(channel_id, session)

    # May also clear the tag if `tag_name` is None.
    channel.set_tag(tag_name)
    channel.flush()
    session.commit()

    # Only move Channel when requested.
    if directory:
        # Move to newly defined directory only if necessary.
        directory.mkdir(parents=True, exist_ok=True)
        if channel.directory != directory:
            coro = channel.move_channel(directory, session, send_events=True)
            if PYTEST:
                await coro
            else:
                background_task(coro)
        else:
            save_channels_config.activate_switch()
    else:
        logger.info(f'Tagging {channel} with {tag_name}')


@optional_session
async def search_channels(tag_names: List[str], session: Session) -> List[Channel]:
    """Search Tagged Channels."""
    from wrolpi.tags import Tag
    channels = session.query(Channel).join(Tag).filter(Tag.name.in_(tag_names)).all()
    return channels
