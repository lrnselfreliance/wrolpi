#! /usr/bin/env python
import argparse
import os
import pathlib
import sys


def count_files(directory: pathlib.Path) -> int:
    count = 0
    for path in directory.iterdir():
        if path.is_dir():
            count += count_files(path)
        else:
            count += 1
    return count


if __name__ == '__main__':
    default_cwd = pathlib.Path(os.getcwd())
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?', default=default_cwd, type=pathlib.Path)

    args = parser.parse_args()

    if not args.directory.is_dir():
        print('Directory does not exist', file=sys.stderr)
        sys.exit(1)

    total_count = count_files(args.directory)
    print(total_count)
