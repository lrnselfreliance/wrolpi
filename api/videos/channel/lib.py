from typing import List

from api.common import save_settings_config, sanitize_link
from api.db import get_db_context
from api.errors import UnknownChannel, UnknownDirectory, APIError, ValidationError
from api.vars import DEFAULT_DOWNLOAD_FREQUENCY
from api.videos.common import get_relative_to_media_directory, make_media_directory, check_for_channel_conflicts
from api.videos.lib import get_channels_config


async def get_minimal_channels() -> List[dict]:
    """
    Get the minimum amount of information necessary about all channels.
    """
    with get_db_context() as (db_conn, db):
        curs = db.get_cursor()

        # Get all channels, even if they don't have videos.
        query = '''
            SELECT
                c.id, name, link, directory, url
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


def delete_channel(link):
    with get_db_context() as (db_conn, db):
        Channel = db['channel']
        channel = Channel.get_one(link=link)
        if not channel:
            raise UnknownChannel()
        with db.transaction(commit=True):
            # Delete all videos in this channel
            curs = db.get_cursor()
            query = 'DELETE FROM video WHERE channel_id = %s'
            curs.execute(query, (channel['id'],))

            # Finally, delete the channel
            channel.delete()

        # Save these changes to the local.yaml as well
        channels = get_channels_config(db)
        save_settings_config(channels)


def update_channel(data, link):
    with get_db_context() as (db_conn, db):
        Channel = db['channel']
        with db.transaction(commit=True):
            channel = Channel.get_one(link=link)

            if not channel:
                raise UnknownChannel()

            # Only update directory if it was empty
            if data.get('directory') and not channel['directory']:
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

            # Verify that the URL/Name/Link aren't taken
            check_for_channel_conflicts(
                db=db,
                id=channel.get('id'),
                url=data.get('url'),
                name=data.get('name'),
                link=data.get('link'),
                directory=data.get('directory'),
            )

            # Apply the changes now that we've OK'd them
            channel.update(data)
            channel.flush()

        # Save these changes to the local.yaml as well
        channels = get_channels_config(db)
        save_settings_config(channels)

    return channel


def get_channel(link) -> dict:
    with get_db_context() as (db_conn, db):
        Channel = db['channel']
        channel = Channel.get_one(link=link)
        if not channel:
            raise UnknownChannel()
        return dict(channel)


def create_channel(data):
    with get_db_context() as (db_conn, db):
        Channel = db['channel']

        # Verify that the URL/Name/Link aren't taken
        try:
            check_for_channel_conflicts(
                db,
                url=data.get('url'),
                name=data['name'],
                link=sanitize_link(data['name']),
                directory=str(data['directory']),
            )
        except APIError as e:
            raise ValidationError from e

        with db.transaction(commit=True):
            channel = Channel(
                name=data['name'],
                url=data.get('url'),
                match=data.get('match_regex'),
                link=sanitize_link(data['name']),
                directory=str(data['directory']),
                download_frequency=data.get('download_frequency', DEFAULT_DOWNLOAD_FREQUENCY),
            )
            channel.flush()

        # Save these changes to the local.yaml as well
        channels = get_channels_config(db)
        save_settings_config(channels)

        return dict(channel)