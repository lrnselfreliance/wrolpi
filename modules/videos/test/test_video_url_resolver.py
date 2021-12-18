import pytest

from modules.videos.video_url_resolver import video_url_resolver


@pytest.mark.parametrize(
    'domain,entry,expected',
    [
        ('youtube.com', {'url': 'foo'}, 'https://youtube.com/watch?v=foo'),
        ('youtube.com', {'webpage_url': 'https://youtube.com/watch?v=foo'}, 'https://youtube.com/watch?v=foo'),
        ('youtube.com', {'url': 'https://youtube.com/watch?v=foo'}, 'https://youtube.com/watch?v=foo'),
    ]
)
def test_video_url_resolver(domain, entry, expected):
    assert video_url_resolver(domain, entry) == expected
