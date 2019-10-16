#! /usr/bin/env python3
import argparse
import logging

from wrolpi.plugins.videos import downloader

PRETTY_NAME = 'Videos'
logger = logging.getLogger('wrolpi')


def init_parser(sub_commands):
    # Called by WROLPI's main() function
    download_parser = sub_commands.add_parser('download')
    download_parser.add_argument('-a', '--all', action='store_true', default=False,
                                 help='Re-check all videos have been downloaded')
    download_parser.add_argument('-c', '--count-limit', type=int, default=0,
                                 help='Download at most this many videos to each channel\'s directory.')


def main(args):
    if args.sub_commands and 'download' in args.sub_commands:
        downloader.main(args)
        return 0


if __name__ == '__main__':
    # If run directly, we'll make our own parser
    parser = argparse.ArgumentParser()
    sub_commands = parser.add_subparsers(title='sub-commands', dest='sub_commands')
    init_parser(sub_commands)
    args = parser.parse_args()
    main(args)
