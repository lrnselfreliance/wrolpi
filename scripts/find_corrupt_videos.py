#! /usr/bin/env python3
"""
Searches the DB for Video records which do not have both video and audio streams.  If a Video still exists at its URL,
it will be automatically re-downloaded.  If a Video cannot be re-downloaded (it has been deleted from its host) you
will be prompted to delete it.
"""
import argparse
import asyncio
import logging
import sys
from typing import List

from yt_dlp.utils import YoutubeDLError

from modules.videos.downloader import VideoDownloader, extract_info
from modules.videos.models import Video
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.downloader import download_manager

logger = logging.getLogger()


def get_total_corrupted_videos() -> int:
    with get_db_curs() as curs:
        stmt = '''
            WITH all_videos AS (
                select v.id, array_agg(s ->> 'codec_type')::TEXT[] AS codec_types
                from video v
                         cross join lateral json_array_elements(ffprobe_json -> 'streams') s
                group by v.id)
            SELECT COUNT(all_videos.id)
            FROM all_videos
            WHERE NOT all_videos.codec_types @> '{audio,video}'::TEXT[]
        '''
        curs.execute(stmt)
        return int(curs.fetchone()[0])


def get_corrupt_videos(limit: int, offset: int) -> List[dict]:
    params = dict(limit=limit, offset=offset)
    with get_db_curs() as curs:
        stmt = '''
            WITH all_videos AS (
                -- Extract 'codec_type' from all 'stream' objects of each video.
                -- {'streams': [{'codec_type': 'video'}, {'codec_type': 'audio'}]} -> {video,audio}
                select v.id, array_agg(s ->> 'codec_type')::TEXT[] AS codec_types
                from video v
                         cross join lateral json_array_elements(ffprobe_json -> 'streams') s
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


def iterate_corrupt_videos() -> List[dict]:
    limit = 20
    offset = 0
    while True:
        videos = get_corrupt_videos(limit, offset)
        offset += limit
        if len(videos) < limit:
            # Ran out of corrupt videos.
            break
        yield videos


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


async def find_corrupt_videos():
    total_corrupted = get_total_corrupted_videos()
    count = 0

    with get_db_session() as session:
        for chunk in iterate_corrupt_videos():
            video_ids = [i['video_id'] for i in chunk]
            videos = session.query(Video).filter(Video.id.in_(video_ids)).all()
            for video in videos:
                print()
                print(f'Video (remaining: {total_corrupted - count}): {video}')
                count += 1
                streams = (await video.get_ffprobe_json())['streams']
                codec_names = [i['codec_name'] for i in streams]
                print(f'codecs: {codec_names}')

                url = video.url
                if url:
                    try:
                        extract_info(url)
                        print(f'Re-downloading')
                        download_manager.create_download(url, VideoDownloader.name, session=session)
                        video.delete()
                        session.commit()
                        continue
                    except YoutubeDLError:
                        logger.error(f'Video cannot be downloaded: {url}')
                        if confirm(f'Delete?  (y/N)'):
                            video.delete()
                            session.commit()
                            continue

                if confirm('Delete?  (y/N)'):
                    video.delete()
                    session.commit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    coro = find_corrupt_videos()
    loop.run_until_complete(coro)
