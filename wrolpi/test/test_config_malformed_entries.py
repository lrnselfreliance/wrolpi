"""A malformed entry in a config (not a mapping, or a key that is not a string) is skipped and counted, so the config
is never saved over it; the rest of the file still imports."""
import pytest

from modules.archive.lib import DomainsSection
from modules.repos.lib import ReposSection
from modules.videos.lib import ChannelDownloadsSection, ChannelsSection
from wrolpi.collections.config import PlaylistItemsSection, PlaylistsSection
from wrolpi.downloader import DownloadsSection
from wrolpi.tags import TagFilesSection, TagsSection, TagZimsSection

MALFORMED = ['a string', 5, ['a', 'list'], None]


def assert_skipped(section, config, valid_key, malformed_count):
    rows, invalid = section.file_rows(config)
    assert valid_key in rows
    assert len(invalid) >= malformed_count, 'every malformed entry must be counted, so the config is not saved over it'


@pytest.mark.parametrize('section,config,valid_key,malformed_count', [
    (PlaylistsSection(), dict(playlists=[*MALFORMED, dict(name=['a', 'list']), dict(name='good')]), 'good', 5),
    (ReposSection(), dict(repos=[*MALFORMED, dict(url=['a', 'list']), dict(url='https://example.com/a/b.git')]),
     'example.com/a/b', 5),
    (DomainsSection(), dict(collections=[*MALFORMED, dict(name=['a', 'list']), dict(name='example.com')]),
     'example.com', 5),
    (ChannelsSection(), dict(channels=[*MALFORMED, dict(name='c', directory=['a', 'list']),
                                       dict(name='good', directory='videos/good')]), 'videos/good', 5),
    (DownloadsSection(), dict(downloads=[*MALFORMED, dict(url=['a', 'list'], downloader='archive'),
                                         dict(url='https://example.com/good', downloader='archive')]),
     'https://example.com/good', 5),
    (TagFilesSection(), dict(tags=dict(one=dict()), tag_files=[*MALFORMED, [['a', 'list'], 'foo.txt'],
                                                               ['one', 'good.txt']]), ('one', 'good.txt'), 5),
    (TagZimsSection(), dict(tags=dict(one=dict()), tag_zims=[*MALFORMED, [['a', 'list'], 'a.zim', 'A'],
                                                             ['one', 'good.zim', 'A']]), ('one', 'good.zim', 'A'), 5),
])
def test_malformed_entries(test_directory, section, config, valid_key, malformed_count):
    assert_skipped(section, config, valid_key, malformed_count)


def test_malformed_tags(test_directory):
    """A Tag whose attributes are not a mapping is skipped and counted."""
    assert_skipped(TagsSection(), dict(tags={'one': dict(color='#fff'), 'two': 'a string', 'three': 5}), 'one', 2)


def test_malformed_playlist_items(test_directory):
    """A playlist's malformed items are skipped and counted; so is an `items` that is not a list."""
    config = dict(playlists=[
        dict(name='good', items=[*MALFORMED, dict(url=['a', 'list']), dict(url='https://example.com/good')]),
        dict(name='bad', items=5),
    ])
    rows, invalid = PlaylistItemsSection().file_rows(config)
    assert list(rows) == [('good', 'url', 'https://example.com/good', None)]
    assert len(invalid) == 6


def test_malformed_channel_downloads(test_directory):
    """A Channel whose `downloads` is not a list keeps its Downloads (counted)."""
    config = dict(channels=[dict(name='good', directory='videos/good', downloads=5)])
    rows, invalid = ChannelDownloadsSection().file_rows(config)
    assert rows == dict()
    assert invalid
