#! /usr/bin/env python3
"""
WROLPi is a self-contained collection of software to help you survive the world Without Rule of Law.

WROLPi is intended to be run on a Raspberry Pi with an optional external drive attached.  It serves up it's own wifi
network so that any person with a laptop/tablet/phone can connect and use the data previously collected by the user.
"""
import argparse
import logging
import sys

from lib import web
from lib.cmd import import_settings_configs, save_settings_configs
from lib.common import logger
from lib.user_plugins import PLUGINS


def update_choices_to_mains(sub_commands, choices_to_mains, sub_main):
    """Associate a sub-command with the provided main, but only if that sub-command hasn't already been claimed
    by another main.  This is a work-around so plugins can define their down cmd-line arguments."""
    for choice in sub_commands.choices:
        if choice not in choices_to_mains:
            choices_to_mains[choice] = sub_main


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='count')

    sub_commands = parser.add_subparsers(title='sub-commands', dest='sub_commands')

    # Web parser is always present
    web_parser = sub_commands.add_parser('web')
    # This dict keeps track of which main will be called for each sub-command
    choices_to_mains = {'web': web.main}
    web.init_parser(web_parser)

    # Setup the plugins' sub-commands
    for plugin_name, plugin in PLUGINS.items():
        plugin.init_parser(sub_commands)
        update_choices_to_mains(sub_commands, choices_to_mains, plugin.main.main)

    args = parser.parse_args()

    if args.verbose == 1:
        logger.info('Setting verbosity to INFO')
        logger.setLevel(logging.INFO)
    elif args.verbose == 2:
        logger.debug('Setting verbosity to DEBUG')
        logger.setLevel(logging.DEBUG)

    # Always update the DB from the configs
    import_settings_configs(PLUGINS)

    if args.sub_commands:
        plugin_main = choices_to_mains[args.sub_commands]
        return_code = plugin_main(args)
    elif args.save_config:
        return_code = save_settings_configs(PLUGINS)
        logger.info('Config written.')
    else:
        parser.print_help()
        return_code = 1

    return return_code


if __name__ == '__main__':
    sys.exit(main())
