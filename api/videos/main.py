#! /usr/bin/env python3
import argparse
import asyncio

from api.videos.api import refresh_videos
from . import downloader

PRETTY_NAME = 'Videos'


def init_parser(sub_commands):
    # Called by WROLPI's main() function
    download_parser = sub_commands.add_parser('download')
    download_parser.add_argument('-a', '--all', action='store_true', default=False,
                                 help='Re-check all videos have been downloaded')
    download_parser.add_argument('-c', '--count-limit', type=int, default=0,
                                 help='Download at most this many videos to each channel\'s directory.')

    content_parser = sub_commands.add_parser('content')
    content_parser.add_argument('-r', '--refresh', nargs='*',
                                help='Search for new videos files.  Specify a channel name.')


async def main(args):
    if args.sub_commands and 'download' in args.sub_commands:
        downloader.main(args)
        return 0
    elif args.sub_commands and 'content' in args.sub_commands:
        refresh = args.refresh
        await refresh_videos(refresh)
        return 0


if __name__ == '__main__':
    # If run directly, we'll make our own parser
    parser = argparse.ArgumentParser()
    sub_commands = parser.add_subparsers(title='sub-commands', dest='sub_commands')
    init_parser(sub_commands)
    args = parser.parse_args()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(args))
