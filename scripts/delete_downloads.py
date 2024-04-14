#! /usr/bin/env python3
import asyncio

from wrolpi.db import get_db_curs
from wrolpi.downloader import get_download_manager_config


async def delete_once_downloads():
    """Deletes all once-downloads."""
    with get_db_curs(commit=True) as curs:
        curs.execute('DELETE FROM download WHERE frequency IS NULL')


async def delete_all_downloads():
    """Deletes all downloads."""
    with get_db_curs(commit=True) as curs:
        curs.execute('DELETE FROM download')  # noqa


async def main():
    """Asks the user which Downloads they want to delete.  Saves the config if any downloads are deleted."""
    need_save = False

    delete_once = input('Delete all once-downloads? (Downloads that will only occur once) [y/N]: ')
    delete_once = True if delete_once.lower() == 'y' else False

    if delete_once:
        await delete_once_downloads()
        need_save = True

    delete_all = input('Delete ALL downloads? [y/N]: ')
    delete_all = True if delete_all.lower() == 'y' else False

    if delete_all:
        await delete_all_downloads()
        need_save = True

    if need_save:
        # Save the config file.
        get_download_manager_config().save()


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
