from typing import List, Dict

from sqlalchemy.orm.exc import NoResultFound

from wrolpi.common import sanitize_link, run_after, get_relative_to_media_directory, make_media_directory
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.errors import UnknownChannel, UnknownDirectory, APIError, ValidationError
from ..common import check_for_channel_conflicts
from ..lib import save_channels_config
from ..models import Channel

DEFAULT_DOWNLOAD_FREQUENCY = 60 * 60 * 24 * 7  # weekly
DEFAULT_DOWNLOAD_TIMEOUT = 60.0 * 10.0  # Ten minutes


async def get_minimal_channels() -> List[dict]:
    """
    Get the minimum amount of information necessary about all channels.
    """
    with get_db_curs() as curs:
        # Get all channels, even if they don't have videos.
        stmt = '''
            SELECT
                c.id, name, link, directory, url, download_frequency, info_date, next_download
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


@run_after(save_channels_config)
def delete_channel(link):
    with get_db_session(commit=True) as session:
        try:
            channel = session.query(Channel).filter_by(link=link).one()
        except NoResultFound:
            raise UnknownChannel()

        channel.delete_with_videos()


@run_after(save_channels_config)
def update_channel(data, link):
    with get_db_session(commit=True) as session:
        try:
            channel = session.query(Channel).filter_by(link=link).one()
        except NoResultFound:
            raise UnknownChannel()

        # Only update directory if it was empty
        if data.get('directory') and not channel.directory:
            try:
                data['directory'] = get_relative_to_media_directory(data['directory'])
            except UnknownDirectory:
                if data['mkdir']:
                    make_media_directory(data['directory'])
                    data['directory'] = get_relative_to_media_directory(data['directory'])
                else:
                    raise

        if 'directory' in data:
            data['directory'] = str(data['directory'])

        if 'download_frequency' in data:
            try:
                data['download_frequency'] = int(data['download_frequency'])
            except ValueError:
                raise APIError('Invalid download frequency')

        if data.get('match_regex') in ('None', 'null'):
            data['match_regex'] = None

        # Verify that the URL/Name/Link aren't taken
        check_for_channel_conflicts(
            session,
            id_=channel.id,
            url=data.get('url'),
            name=data.get('name'),
            link=data.get('link'),
            directory=data.get('directory'),
        )

        # Apply the changes now that we've OK'd them
        channel.update(data)

    return channel


def get_channel(link) -> dict:
    """
    Get a Channel by it's `link`.  Raise UnknownChannel if it does not exist.
    """
    with get_db_session() as session:
        try:
            channel = session.query(Channel).filter_by(link=link).one()
        except NoResultFound:
            raise UnknownChannel()
        return channel.dict()


@run_after(save_channels_config)
def create_channel(data: dict) -> dict:
    """
    Create a new Channel.  Check for conflicts with existing Channels.
    """
    with get_db_session(commit=True) as session:
        try:
            # Verify that the URL/Name/Link aren't taken
            check_for_channel_conflicts(
                session,
                url=data.get('url'),
                name=data['name'],
                link=sanitize_link(data['name']),
                directory=str(data['directory']),
            )
        except APIError as e:
            raise ValidationError() from e

        channel = Channel(
            name=data['name'],
            url=data.get('url'),
            match_regex=data.get('match_regex'),
            link=sanitize_link(data['name']),
            directory=str(data['directory']),
            download_frequency=data.get('download_frequency', DEFAULT_DOWNLOAD_FREQUENCY),
        )
        session.add(channel)
        session.commit()
        session.flush()
        session.refresh(channel)

        return channel.dict()
