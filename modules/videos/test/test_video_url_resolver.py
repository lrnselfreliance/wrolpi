import pytest

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
