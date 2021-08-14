from datetime import datetime
from typing import List

from sqlalchemy.orm.exc import NoResultFound

from api.common import sanitize_link, run_after
from api.db import get_db_context, get_db_curs
from api.errors import UnknownChannel, UnknownDirectory, APIError, ValidationError
from api.vars import DEFAULT_DOWNLOAD_FREQUENCY
from api.videos.common import get_relative_to_media_directory, make_media_directory, check_for_channel_conflicts
from api.videos.lib import save_channels_config
from api.videos.models import Channel


async def get_minimal_channels() -> List[dict]:
    """
    Get the minimum amount of information necessary about all channels.
    """
    with get_db_curs() as curs:
        # Get all channels, even if they don't have videos.
        query = '''
            SELECT
                c.id, name, link, directory, url, download_frequency, info_date, next_download
            FROM
                channel AS c
            ORDER BY LOWER(name)
        '''
        curs.execute(query)
        channels = list(map(dict, curs.fetchall()))

        # Add video counts to all channels
        query = '''
            SELECT
                c.id, COUNT(v.id) AS video_count
            FROM
                channel AS c
                LEFT JOIN video AS v ON v.channel_id = c.id
            WHERE
                v.video_path IS NOT NULL
            GROUP BY 1
        '''
        curs.execute(query)
        video_counts = {i['id']: i['video_count'] for i in curs.fetchall()}

        for channel in channels:
            channel_id = channel['id']
            try:
                channel['video_count'] = video_counts[channel_id]
            except KeyError:
                # No videos for this channel
                channel['video_count'] = 0

    return channels


@run_after(save_channels_config)
def delete_channel(link):
    with get_db_context(commit=True) as (engine, session):
        try:
            channel = session.query(Channel).filter_by(link=link).one()
        except NoResultFound:
            raise UnknownChannel()

        channel.delete_with_videos()


@run_after(save_channels_config)
def update_channel(data, link):
    with get_db_context(commit=True) as (engine, session):
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
    with get_db_context() as (engine, session):
        try:
            channel = session.query(Channel).filter_by(link=link).one()
        except NoResultFound:
            raise UnknownChannel()
        return channel


@run_after(save_channels_config)
def create_channel(data: dict) -> Channel:
    """
    Create a new Channel.  Check for conflicts with existing Channels.
    """
    with get_db_context(commit=True) as (engine, session):
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

    return channel
