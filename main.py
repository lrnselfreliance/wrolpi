#! /usr/bin/env python3
"""
WROLPi is a self-contained collection of software to help you survive the world Without Rule of Law.

WROLPi is intended to be run on a Raspberry Pi with an optional external drive attached.  It serves up it's own wifi
network so that any person with a laptop/tablet/phone can connect and use the data previously collected by the user.
"""
import argparse
import logging
import sys

from lib import api
from lib.cmd import import_settings_configs, save_settings_configs
from lib.common import logger
from lib.modules import MODULES


def update_choices_to_mains(sub_commands, choices_to_mains, sub_main):
    """Associate a sub-command with the provided main, but only if that sub-command hasn't already been claimed
    by another main.  This is a work-around so modules can define their down cmd-line arguments."""
    for choice in sub_commands.choices:
        if choice not in choices_to_mains:
            choices_to_mains[choice] = sub_main


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='count')

    sub_commands = parser.add_subparsers(title='sub-commands', dest='sub_commands')

    # API parser is always present
    api_parser = sub_commands.add_parser('api')
    # This dict keeps track of which main will be called for each sub-command
    choices_to_mains = {'api': api.main}
    api.init_parser(api_parser)

    # Setup the modules' sub-commands
    for module_name, module in MODULES.items():
        module.init_parser(sub_commands)
        update_choices_to_mains(sub_commands, choices_to_mains, module.main.main)

    args = parser.parse_args()

    if args.verbose == 1:
        logger.info('Setting verbosity to INFO')
        logger.setLevel(logging.INFO)
    elif args.verbose == 2:
        logger.debug('Setting verbosity to DEBUG')
        logger.setLevel(logging.DEBUG)

    # Always warn about the log level so we know what will be logged
    logger.warning(f'Logging level: {logger.getEffectiveLevel()}')

    # Always update the DB from the configs
    import_settings_configs(MODULES)

    if args.sub_commands:
        module_main = choices_to_mains[args.sub_commands]
        return_code = module_main(args)
    elif args.save_config:
        return_code = save_settings_configs(MODULES)
        logger.info('Config written.')
    else:
        parser.print_help()
        return_code = 1

    return return_code


if __name__ == '__main__':
    sys.exit(main())
