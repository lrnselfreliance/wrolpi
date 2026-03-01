#! /usr/bin/env python3
"""One-time script to clean up orphaned hardlinks in the tags directory.

These are files that remain after content was re-downloaded with new timestamps
or filenames were sanitized. They have st_nlink==1 meaning the tags directory
copy is the only remaining copy.

Usage:
    python scripts/cleanup_orphaned_tags.py           # Dry run - shows what would be deleted
    python scripts/cleanup_orphaned_tags.py --delete  # Actually delete the files
"""
import argparse
import os
import sys

sys.path.append(os.getcwd())

from wrolpi.common import walk
from wrolpi.vars import MEDIA_DIRECTORY


def cleanup_orphaned_tags(dry_run: bool = True) -> list:
    """Find and optionally delete orphaned hardlinks in the tags directory.

    Orphaned files are those with st_nlink == 1, meaning the tags directory
    copy is the only copy (the original source was deleted/replaced).
    """
    tags_dir = MEDIA_DIRECTORY / 'tags'

    if not tags_dir.exists():
        print(f'Tags directory does not exist: {tags_dir}')
        return []

    deleted = []
    for file in walk(tags_dir):
        if not file.is_file():
            continue
        # Skip README.txt
        if file.name == 'README.txt':
            continue
        try:
            if file.stat().st_nlink == 1:
                if dry_run:
                    print(f'Would delete: {file}')
                else:
                    print(f'Deleting: {file}')
                    file.unlink()
                deleted.append(file)
        except OSError as e:
            print(f'Error checking {file}: {e}')

    action = "Would delete" if dry_run else "Deleted"
    print(f'\n{action} {len(deleted)} orphaned files')
    return deleted


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Clean up orphaned hardlinks in the tags directory.')
    parser.add_argument('--delete', action='store_true', default=False,
                        help='Actually delete the orphaned files (default is dry run)')
    args = parser.parse_args()

    dry_run = not args.delete
    if dry_run:
        print('DRY RUN - add --delete to actually remove files\n')
    cleanup_orphaned_tags(dry_run=dry_run)
