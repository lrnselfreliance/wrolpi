#! /usr/bin/env python3
"""
This module will be the entry-point for your plugin.  The lib.main will expect these basic functions to be here.  Add
onto them to build your plugin.

Required: PRETTY_NAME, init_parser, main
"""
import argparse
import logging

# Pretty Name will be displayed when your plugin is linked to in the UI
PRETTY_NAME = 'Map'
logger = logging.getLogger('lib')


def init_parser(sub_commands):
    # This function is called by WROLPI's main() function during startup, use it to setup your
    # command-line arguments.  If you don't have any, put a "pass" here
    download_parser = sub_commands.add_parser('example_plugin')
    # Add your own arguments
    download_parser.add_argument('-a', '--asdf', action='store_true', default=False, help='Asdf')


def main(args):
    # This function will be called when the parsers you defined above are passed via the command-line.
    if args.sub_commands and 'example_plugin' in args.sub_commands:
        print(f'hello {hello()}!')
        return 0


def import_settings_config():
    # If you build a config, it will be imported on startup here
    pass


def save_settings_config():
    # This could be called by the command-line to save the DB settings to a config.
    pass


if __name__ == '__main__':
    # If run directly, we'll make our own parser in the same form that lib.main does
    parser = argparse.ArgumentParser()
    sub_commands = parser.add_subparsers(title='sub-commands', dest='sub_commands')
    init_parser(sub_commands)
    args = parser.parse_args()
    main(args)
