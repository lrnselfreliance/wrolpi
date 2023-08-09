#! /usr/bin/env python3
"""
Searches the DB for Video records which do not have both video and audio streams.  If a Video still exists at its URL,
it will be automatically re-downloaded.  If a Video cannot be re-downloaded (it has been deleted from its host) you
will be prompted to delete it.
"""
import argparse
import asyncio
import logging
import pathlib
import subprocess
import sys
import tempfile
from http import HTTPStatus
from typing import List

import aiohttp
from sqlalchemy.orm import Session
from yt_dlp.utils import YoutubeDLError

from modules.videos.common import ffmpeg_video_complete
from modules.videos.downloader import extract_info, VideoDownloader
from modules.videos.models import Video, Channel
from wrolpi.dates import seconds_to_timestamp
from wrolpi.db import get_db_session, get_db_curs

logger = logging.getLogger()


def get_incomplete_videos(limit: int, offset: int, channel_id: int) -> List[dict]:
    """Returns Video records that do not have both video and audio streams."""
    params = dict(limit=limit, offset=offset, channel_id=channel_id)
    with get_db_curs() as curs:
        stmt = '''
            WITH all_videos AS (
                -- Extract 'codec_type' from all 'stream' objects of each video.
                -- {'streams': [{'codec_type': 'video'}, {'codec_type': 'audio'}]} -> {video,audio}
                select v.id, array_agg(s ->> 'codec_type')::TEXT[] AS codec_types
                from video v
                         cross join lateral json_array_elements(ffprobe_json -> 'streams') s
                         where channel_id = %(channel_id)s
                group by v.id)
            SELECT all_videos.id AS video_id, fg.primary_path, all_videos.codec_types
            FROM all_videos
                     LEFT JOIN video v ON v.id = all_videos.id
                     LEFT JOIN public.file_group fg on fg.id = v.file_group_id
            -- Filter out videos that have video AND audio streams.
            WHERE NOT all_videos.codec_types @> '{video,audio}'::TEXT[]
              AND fg.primary_path like '/media/wrolpi/videos/%%'
            ORDER BY all_videos.id
            LIMIT %(limit)s
            OFFSET %(offset)s
        '''
        curs.execute(stmt, params)
        return [dict(i) for i in curs.fetchall()]


def iterate_incomplete_videos(channel_id: int = None) -> List[dict]:
    limit = 20
    offset = 0
    with get_db_session() as session:
        channel_ids = [channel_id, ] if channel_id else [int(i[0]) for i in session.query(Channel.id)]
        found = False
        for channel_id in channel_ids:
            channel_id: int
            while True:
                videos = get_incomplete_videos(limit, offset, channel_id)
                offset += limit
                if videos:
                    yield videos
                if len(videos) < limit:
                    # Ran out of corrupt videos.
                    if found:
                        logger.debug(f'Ran out of corrupt videos for {channel_id=}')
                    else:
                        logger.debug(f'No corrupt videos for {channel_id=}')
                    break


def confirm(msg: str) -> bool:
    while True:
        input_ = input(msg)
        if input_ == 'y':
            return True
        if input_ == 'q':
            print('Quitting...')
            sys.exit(0)
        if not input_ or input_ == 'n':
            return False


def can_be_downloaded(url: str) -> bool:
    try:
        extract_info(url)
        return True
    except YoutubeDLError:
        return False


async def create_download(url: str, downloader: str):
    json_ = {'urls': url, 'downloader': downloader}
    async with aiohttp.ClientSession() as session:
        async with session.post('http://127.0.0.1:8080/api/download', json=json_) as response:
            if response.status == HTTPStatus.NO_CONTENT:
                logger.info(f'Created download for {url}')
            else:
                raise Exception(f'Failed to create download for {url}')


async def download_or_ask_delete(video: Video, session: Session, delete_message: str):
    if video.url and can_be_downloaded(video.url):
        await create_download(video.url, VideoDownloader.name)
        # Always re-download when possible.
        do_delete = True
    else:
        logger.error(f'Video cannot be downloaded: {video.url or video}')
        do_delete = confirm(delete_message)

    if do_delete:
        logger.debug(f'Deleting {video}')
        video.delete(add_to_skip_list=False)
        session.commit()


async def find_corrupt_videos(channel_id: int = None):
    with get_db_session() as session:
        for chunk in iterate_incomplete_videos(channel_id=channel_id):
            video_ids = [i['video_id'] for i in chunk]
            videos = session.query(Video).filter(Video.id.in_(video_ids)).all()
            for video in videos:
                path = video.video_path
                await download_or_ask_delete(video, session, f'Missing audio. {path}  Delete? (y/N)')

    with get_db_session() as session:
        videos = session.query(Video).filter(Video.validated == False)  # noqa
        if channel_id:
            videos = videos.filter(Video.channel_id == channel_id)
        for video in videos:
            if not video.duration:
                logger.warning(f'No duration for {video}')
                continue
            if ffmpeg_video_complete(video.video_path):
                logger.debug(f'{video.video_path.name} is valid')
                video.validated = True
                session.commit()
                continue

            path = video.video_path
            await download_or_ask_delete(video, session, f'Corrupt video. {path}  Delete? (y/N)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', action='count')
    parser.add_argument('-c', '--channel-id', type=int,
                        help='The id of the channel to search')
    args = parser.parse_args()

    if args.v == 0:
        logger.setLevel(logging.WARNING)
    elif args.v == 1:
        logger.setLevel(logging.INFO)
    elif args.v >= 2:
        logger.setLevel(logging.DEBUG)
        logger.debug(f'Debug logging')

    loop = asyncio.get_event_loop()
    coro = find_corrupt_videos(channel_id=args.channel_id)
    loop.run_until_complete(coro)
