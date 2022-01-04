from collections import defaultdict
from datetime import timedelta
from typing import List, Dict, Union, Generator

from sqlalchemy.orm.exc import NoResultFound

from wrolpi.common import sanitize_link, run_after, get_relative_to_media_directory, make_media_directory, logger
from wrolpi.dates import today
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.downloader import download_manager
from wrolpi.errors import UnknownChannel, UnknownDirectory, APIError, ValidationError, InvalidDownload
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
                c.id, name, link, directory, url, download_frequency, info_date
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


def get_channel(source_id: str = None, link: str = None, url: str = None, return_dict: bool = True) -> COD:
    """
    Attempt to find a Channel using the provided params.  The params are in order of reliability.

    Raises UnknownChannel if no channel is found.
    """
    with get_db_session() as session:
        channel: COD = None  # noqa
        # Try by source_id first.
        if source_id:
            channel = session.query(Channel).filter_by(source_id=source_id).one_or_none()
        if not channel and link:
            channel = session.query(Channel).filter_by(link=link).one_or_none()
        if not channel and url:
            channel = session.query(Channel).filter_by(url=url).one_or_none()

        if not channel:
            raise UnknownChannel(f'No channel matches {link=} {source_id=} {url=}')

        logger.debug(f'Found {channel=} using {source_id=} {link=} {url=}')
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


def spread_channel_downloads():
    """
    Channels should be downloaded in a manner that is spread out over their frequency.  For example, three channels
    with a frequency of a week should be downloaded on different days that week.
    """
    with get_db_session(commit=True) as session:
        channels = list(session.query(Channel).filter(
            Channel.url != None,
            Channel.url != '',
            Channel.download_frequency != None
        ).order_by(Channel.link).all())  # noqa

        url_next_download = _spread_by_frequency(channels)

        for info in url_next_download:
            url, frequency, next_download = info['url'], info['frequency'], info['next_download']
            download = download_manager.get_or_create_download(url, session)
            download.downloader = 'video_channel'
            download.frequency = frequency
            download.next_download = next_download


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
                if data['download_frequency'] in ('null', 'None', ''):
                    data['download_frequency'] = None
                else:
                    raise APIError(f'Invalid download frequency {data["download_frequency"]}')

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

    spread_channel_downloads()

    return channel


@run_after(save_channels_config)
@run_after(spread_channel_downloads)
def create_channel(data: dict, return_dict: bool = True) -> Union[Channel, dict]:
    """
    Create a new Channel.  Check for conflicts with existing Channels.
    """
    with get_db_session(commit=True) as session:
        link = sanitize_link(data['name'])
        try:
            # Verify that the URL/Name/Link aren't taken
            check_for_channel_conflicts(
                session,
                url=data.get('url'),
                name=data['name'],
                link=link,
                directory=str(data['directory']),
                source_id=data.get('source_id'),
            )
        except APIError as e:
            raise ValidationError() from e

        channel = Channel(
            name=data['name'],
            url=data.get('url'),
            match_regex=data.get('match_regex'),
            link=link,
            directory=str(data['directory']),
            download_frequency=data.get('download_frequency'),
            source_id=data.get('source_id'),
        )
        session.add(channel)
        session.commit()
        session.flush()
        session.refresh(channel)

        if return_dict:
            return channel.dict()
        else:
            return channel


@run_after(save_channels_config)
def delete_channel(link):
    with get_db_session(commit=True) as session:
        try:
            channel = session.query(Channel).filter_by(link=link).one()
        except NoResultFound:
            raise UnknownChannel()

        channel.delete_with_videos()


def download_channel(link: str):
    """
    Create a Download record for a Channel's entire catalog.
    """
    channel = get_channel(link=link, return_dict=False)
    with get_db_session(commit=True) as session:
        if not download_manager.get_download(session, channel.url):
            raise InvalidDownload(f'Channel {channel.name} does not have a download!')

        download_manager.create_download(channel.url, session, downloader='video_channel')
