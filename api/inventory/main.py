#! /usr/bin/env python3
import argparse
import logging

PRETTY_NAME = 'Inventory'
logger = logging.getLogger(__name__)


def init_parser(sub_commands):
    pass


def main(args):
    pass


if __name__ == '__main__':
    # If run directly, we'll make our own parser in the same form that api.main does
    parser = argparse.ArgumentParser()
    sub_commands = parser.add_subparsers(title='sub-commands', dest='sub_commands')
    init_parser(sub_commands)
    args = parser.parse_args()
    main(args)
