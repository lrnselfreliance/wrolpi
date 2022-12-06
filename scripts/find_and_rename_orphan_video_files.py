#! /usr/bin/env python3
import argparse
import os
import pathlib
import sys
from typing import List, Dict

sys.path.append(os.getcwd())

from modules.videos import lib as videos_lib
from wrolpi.common import get_media_directory
from wrolpi.files.lib import get_mimetype, split_path_stem_and_suffix


def group_orphaned_files(orphaned_paths: List[pathlib.Path]) -> Dict[str, List[pathlib.Path]]:
    """Group files by the `source_id` in their filename."""
    groups = dict()
    for orphan in orphaned_paths:
        channel, upload_date, source_id, name = videos_lib.parse_video_file_name(orphan)
        if source_id:
            try:
                groups[source_id].append(orphan)
            except KeyError:
                groups[source_id] = [orphan, ]
    return groups


def find_videos(directory: pathlib.Path, source_id: str):
    """Find all video files that match the `source_id`."""
    paths = directory.glob(f'*{source_id}*')
    videos = list(filter(lambda i: get_mimetype(i).startswith('video/'), paths))
    return videos


def main(videos_directory: pathlib.Path, move: bool = False, delete_existing: bool = False,
         delete_orphan: bool = False):
    # Get a list of orphaned files from the DB.  (A file refresh is required for this to work).
    orphaned_files = videos_lib.find_orphaned_video_files(videos_directory)
    orphaned_files = list(orphaned_files)

    # Protect video files absolutely.
    if any(get_mimetype(i).startswith('video/') for i in orphaned_files):
        print(f'Refusing to process video files!', file=sys.stderr)
        sys.exit(1)

    # Group files by the `source_id` in their filename.
    orphaned_file_groups = group_orphaned_files(orphaned_files)

    for source_id, group in orphaned_file_groups.items():
        first = group[0]
        parent = first.parent
        stem, _ = split_path_stem_and_suffix(first)

        video_files = find_videos(parent, source_id)
        video_stems = [split_path_stem_and_suffix(i)[0] for i in video_files]

        if not video_stems:
            if not delete_orphan:
                for orphan in group:
                    print(f'Could not find video file with matching source_id ({source_id}) for {orphan}',
                          file=sys.stderr)
            else:
                for orphan in group:
                    print(f'Deleting: {orphan}')
                    orphan.unlink()
            continue

        if len(set(video_stems)) > 1:
            group = list(map(str, group))
            print(f'Multiple videos match the source_id ({source_id}).  Do not know which to rename to.',
                  file=sys.stderr)
            print(f'Files: {group}', file=sys.stderr)
            continue

        video_stem = video_stems[0]
        for orphan in group:
            orphan_suffix = split_path_stem_and_suffix(orphan.name)[1].lstrip('.')
            if not orphan_suffix:
                print(f'Unable to parse file name {orphan}', file=sys.stderr)
                continue

            destination = pathlib.Path(f'{parent / video_stem}.{orphan_suffix}')

            try:
                if destination.is_file():
                    if delete_existing:
                        print(f'Deleting: {orphan}')
                        orphan.unlink()
                    else:
                        print(f'Destination already exists! {orphan}', file=sys.stderr)
                    continue

                print(f'{repr(str(orphan))} => {repr(str(destination))}')

                if move:
                    orphan.rename(destination)

                    if orphan.is_file() or not destination.is_file():
                        # Something is very wrong, quit.
                        print(f'Failed to rename orphan!  {orphan}', file=sys.stderr)
                        sys.exit(2)
            except OSError as e:
                if 'File name too long' in str(e):
                    print(f'Failed to rename orphan, name is too long!  {destination}')
                    continue
                raise


if __name__ == '__main__':
    media_directory = get_media_directory()

    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', default=media_directory / 'videos', type=pathlib.Path)
    parser.add_argument('-m', '--move', default=False, action='store_true',
                        help='Rename files when a match is found.')
    parser.add_argument('-d', '--delete-existing', default=False, action='store_true',
                        help='Delete files if their matching video file already has that file.')
    parser.add_argument('-o', '--delete-orphan', default=False, action='store_true',
                        help='Delete files which have no matching video file.')
    args = parser.parse_args()

    if not args.directory.is_dir():
        print('Invalid directory', file=sys.stderr)
        sys.exit(1)

    main(
        args.directory,
        args.move,
        args.delete_existing,
        args.delete_orphan,
    )
