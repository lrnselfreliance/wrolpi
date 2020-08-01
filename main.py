#! /usr/bin/env python3
"""
WROLPi is a self-contained collection of software to help you survive the world Without Rule of Law.

WROLPi is intended to be run on a Raspberry Pi with an optional external drive attached.  It serves up it's own wifi
network so that any person with a laptop/tablet/phone can connect and use the data previously collected by the user.
"""
import argparse
import logging
import sys

from api import api
from api.cmd import import_settings_configs
from api.common import logger
from api.modules import MODULES
from api.videos.common import verify_config


def update_choices_to_mains(sub_commands, choices_to_mains, sub_main):
    """Associate a sub-command with the provided main, but only if that sub-command hasn't already been claimed
    by another main.  This is a work-around so modules can define their down cmd-line arguments."""
    for choice in sub_commands.choices:
        if choice not in choices_to_mains:
            choices_to_mains[choice] = sub_main


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='count')
    parser.add_argument('--verify-config', action='store_true', default=False,
                        help='Verify the local.yaml, then exit.')

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

    if args.verify_config:
        verify_config()
        print('Config verified')
        return 0

    if args.verbose == 1:
        logger.info('Setting verbosity to INFO')
        logger.setLevel(logging.INFO)
    elif args.verbose and args.verbose >= 2:
        logger.debug('Setting verbosity to DEBUG')
        logger.setLevel(logging.DEBUG)

    # Always warn about the log level so we know what will be logged
    logger.warning(f'Logging level: {logger.getEffectiveLevel()}')

    import_settings_configs(MODULES)

    if args.sub_commands:
        module_main = choices_to_mains[args.sub_commands]
        return_code = module_main(args)
    else:
        parser.print_help()
        return_code = 1

    return return_code


if __name__ == '__main__':
    sys.exit(main())
