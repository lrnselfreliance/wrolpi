import pytest

from modules.videos.common import get_youtube_channel_id
from modules.videos.normalize_video_url import normalize_video_url


@pytest.mark.parametrize(
    'url,expected',
    [
        ('https://example.com', 'https://example.com'),
        ('https://www.youtube.com/watch?v=0xfMLNVFq2Y', 'https://www.youtube.com/watch?v=0xfMLNVFq2Y'),
        ('https://www.youtube.com/shorts/0xfMLNVFq2Y', 'https://www.youtube.com/watch?v=0xfMLNVFq2Y'),
        ('https://youtu.be/0xfMLNVFq2Y', 'https://www.youtube.com/watch?v=0xfMLNVFq2Y'),
        ('https://youtu.be/0xfMLNVFq2Y', 'https://www.youtube.com/watch?v=0xfMLNVFq2Y'),
        (
                'https://www.youtube.com/watch?v=0xfMLNVFq2Y&list=PLMRyOtjhfFJUMPtB122lfeXebndQaePSF&index=2',
                'https://www.youtube.com/watch?v=0xfMLNVFq2Y'
        ),
        ('https://youtu.be/0xfMLNVFq2Y?si=YALbJCpBgQcoY_Dp', 'https://www.youtube.com/watch?v=0xfMLNVFq2Y')
    ]
)
def test_normalize_video_url(url: str, expected: str):
    assert normalize_video_url(url) == expected


@pytest.mark.parametrize(
    'url,expected',
    [
        ('https://www.youtube.com/channel/UC4t8bw1besFTyjW7ZBCOIrw', 'UC4t8bw1besFTyjW7ZBCOIrw'),
        ('https://www.youtube.com/channel/UC4t8bw1besFTyjW7ZBCOIrw/videos', 'UC4t8bw1besFTyjW7ZBCOIrw'),
        ('https://www.youtube.com/channel/UC4t8bw1besFTyjW7ZBCOIrw/', 'UC4t8bw1besFTyjW7ZBCOIrw'),
        ('https://m.youtube.com/channel/UC4t8bw1besFTyjW7ZBCOIrw', 'UC4t8bw1besFTyjW7ZBCOIrw'),
        ('https://www.youtube.com/@wrolpi', None),
        ('https://www.youtube.com/@wrolpi/featured', None),
        ('https://www.youtube.com/@wrolpi/videos', None),
        ('https://www.youtube.com/@wrolpi/playlists', None),
        ('https://example.com/channel/something', None),
    ]
)
def test_get_youtube_channel_id(url: str, expected):
    assert get_youtube_channel_id(url) == expected
