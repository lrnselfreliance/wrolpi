from functools import lru_cache

from wrolpi.common import get_media_directory


@lru_cache(maxsize=1)
def get_archive_directory():
    return get_media_directory() / 'archive'


def new_archive(url):
    pass
