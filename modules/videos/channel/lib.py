import pathlib
from pathlib import Path
from typing import List, Union

from sqlalchemy import or_, func, desc, asc
from sqlalchemy.orm import Session, joinedload

from wrolpi import flags
from wrolpi.collections import Collection
from wrolpi.common import logger, \
    get_media_directory, wrol_mode_check, background_task
from wrolpi.db import get_db_curs, get_db_session
from wrolpi.downloader import save_downloads_config, download_manager, Download
from wrolpi.errors import APIError, ValidationError, RefreshConflict
from wrolpi.events import Events
from wrolpi.tags import Tag
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
                      col.name AS "name",
                      col.directory,
                      c.url,
                      t.name   AS "tag_name",
                      c.video_count,
                      c.total_size,
                      c.minimum_frequency
               FROM channel AS c
                        INNER JOIN collection col ON col.id = c.collection_id
                        LEFT JOIN tag t ON t.id = col.tag_id
               '''
        curs.execute(stmt)
        logger.debug(stmt)
        channels = sorted([dict(i) for i in curs.fetchall()], key=lambda i: i['name'].lower())

    return channels


COD = Union[dict, Channel]


def get_channel(session: Session, *, channel_id: int = None, source_id: str = None, url: str = None,
                directory: str = None, name: str = None, return_dict: bool = True) -> COD:
    """
    Attempt to find a Channel using the provided params.  The params are in order of reliability.

    Raises UnknownChannel if no channel is found.
    """
    channel: COD = None  # noqa
    # Try to find the channel by the most reliable methods first.
    # Always eagerly load Collection to ensure name/directory/tag_id are available
    if channel_id:
        channel = session.query(Channel).options(joinedload(Channel.collection)).filter_by(id=channel_id).one_or_none()
    if not channel and source_id:
        channel = session.query(Channel).options(joinedload(Channel.collection)).filter_by(
            source_id=source_id).one_or_none()
    if not channel and url:
        channel = session.query(Channel).options(joinedload(Channel.collection)).filter_by(url=url).one_or_none()
    if not channel and directory:
        directory = Path(directory)
        if not directory.is_absolute():
            directory = get_media_directory() / directory
        channel = session.query(Channel).join(Collection).filter(
            Collection.directory == str(directory)).one_or_none()
    if not channel and name:
        channel = session.query(Channel).join(Collection).filter(Collection.name == name).one_or_none()

    if not channel:
        raise UnknownChannel(f'No channel matches {channel_id=} {source_id=} {url=} {directory=}')

    logger.debug(f'Found {channel=} using {channel_id=} {source_id=} {url=} {directory=}')
    session.refresh(channel)
    if return_dict:
        statistics = channel.get_statistics()
        channel = channel.dict()
        channel['statistics'] = statistics
    return channel


async def update_channel(session: Session, *, data: schema.ChannelPutRequest, channel_id: int) -> Channel:
    """Update a Channel's DB record"""
    channel = Channel.find_by_id(session, channel_id)

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

    if new_directory != old_directory:
        if not new_directory.is_dir():
            new_directory.mkdir(parents=True)

        # Always use background task with its own session to avoid
        # DetachedInstanceError when the original session is closed.
        background_task(_background_move_channel(channel.id, new_directory))

    save_channels_config.activate_switch()

    return channel


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

    # Create Collection first
    collection = Collection(
        name=data.name,
        kind='channel',
        directory=directory,
    )
    session.add(collection)
    session.flush([collection])

    # Create Channel linked to Collection
    channel = Channel(collection_id=collection.id)
    session.add(channel)
    session.flush([channel])
    # Apply the changes now that we've OK'd them
    channel.update(data.__dict__)

    session.commit()

    save_channels_config.activate_switch()

    return channel.dict() if return_dict else channel


def delete_channel(session: Session, *, channel_id: int):
    channel = Channel.find_by_id(session, channel_id)

    channel_dict = channel.dict()
    channel.delete_with_videos()

    save_channels_config.activate_switch()

    return channel_dict


async def search_channels_by_name(session: Session, name: str, limit: int = 5,
                                  order_by_video_count: bool = False) -> List[Channel]:
    name = name or ''
    name_no_spaces = ''.join(name.split(' '))
    if order_by_video_count:
        stmt = session.query(Channel, func.count(Video.id).label('video_count')) \
            .join(Collection) \
            .filter(or_(
            Collection.name.ilike(f'%{name}%'),
            Collection.name.ilike(f'%{name_no_spaces}%'),
        )) \
            .outerjoin(Video, Video.channel_id == Channel.id) \
            .group_by(Channel.id, Collection.id, Collection.name) \
            .order_by(desc('video_count'), asc(Collection.name)) \
            .limit(limit)
        channels = [i[0] for i in stmt]
    else:
        stmt = session.query(Channel) \
            .join(Collection) \
            .filter(or_(
            Collection.name.ilike(f'%{name}%'),
            Collection.name.ilike(f'%{name_no_spaces}%'),
        )) \
            .order_by(asc(Collection.name)) \
            .limit(limit)
        channels = stmt.all()
    return channels


@wrol_mode_check
async def create_channel_download(channel_id: int, url: str, frequency: int, settings: dict):
    """Create Download for Channel."""
    with get_db_session(commit=True) as session:
        channel = Channel.find_by_id(session, channel_id)
        download = channel.get_or_create_download(session, url, frequency, reset_attempts=True)
        download.settings = settings

    save_channels_config.activate_switch()
    save_downloads_config.activate_switch()

    return download


@wrol_mode_check
async def update_channel_download(channel_id: int, download_id: int, url: str, frequency: int, settings: dict):
    """Fetch Channel's Download, update its properties."""
    with get_db_session(commit=True) as session:
        # Ensure that the Channel exists.
        Channel.find_by_id(session, channel_id)
        download = Download.find_by_id(session, download_id)
        download.url = url
        download.frequency = frequency
        download.settings = settings
        session.commit()

    download_manager.remove_from_skip_list(url)

    save_channels_config.activate_switch()
    save_downloads_config.activate_switch()

    return download


async def _background_move_channel(channel_id: int, target_directory: pathlib.Path):
    """Helper to run channel move in background with its own database session.

    This allows the move to continue even if the original HTTP request is cancelled
    (e.g., user closes browser tab), and avoids DetachedInstanceError by creating
    a fresh session for the background task.
    """
    try:
        with get_db_session(commit=True) as session:
            channel = Channel.find_by_id(session, channel_id)
            if not channel:
                logger.error(f'_background_move_channel: channel {channel_id} not found')
                Events.send_file_move_failed(f'Channel move failed: channel not found')
                return
            await channel.move_channel(target_directory, session, send_events=True)
    except Exception as e:
        logger.error(f'_background_move_channel: failed for channel_id={channel_id}', exc_info=e)
        Events.send_file_move_failed(f'Channel move failed: {e}')


@wrol_mode_check
async def tag_channel(session: Session, tag_name: str | None, directory: pathlib.Path | None, channel_id: int):
    """Add a Tag to a Channel, or remove a Tag from a Channel if no `tag_name` is provided.

    Move the Channel to the new directory, if provided."""
    if directory and flags.refreshing.is_set():
        raise RefreshConflict('Refusing to move channel while file refresh is in progress')

    channel = Channel.find_by_id(session, channel_id)

    # May also clear the tag if `tag_name` is None.
    channel.set_tag(tag_name)
    channel.flush()
    session.commit()

    # Only move Channel when requested.
    if directory:
        # Move to newly defined directory only if necessary.
        directory.mkdir(parents=True, exist_ok=True)
        if channel.directory != directory:
            # Always use background task with its own session to avoid
            # DetachedInstanceError when the original session is closed.
            background_task(_background_move_channel(channel.id, directory))
        else:
            save_channels_config.activate_switch()
    else:
        logger.info(f'Tagging {channel} with {tag_name}')
        # Always save config when tag changes, even without directory
        save_channels_config.activate_switch()


async def search_channels(session: Session, tag_names: List[str]) -> List[Channel]:
    """Search Tagged Channels."""
    channels = session.query(Channel).join(Collection).join(Tag).filter(Tag.name.in_(tag_names)).all()
    return channels
