import pytest

from wrolpi import captions


def test_get_caption_text(vtt_file1, srt_file3):
    expected = ['okay welcome to this session this is',
                'okay welcome to this session this is\ncalled the kinetic bunny need to meet',
                'called the kinetic bunny need to meet',
                'called the kinetic bunny need to meet\nthe virtual bonnie emilio stop this is',
                'the virtual bonnie emilio stop this is',
                'the virtual bonnie emilio stop this is\njana car who just to give a little bit',
                'jana car who just to give a little bit',
                'jana car who just to give a little bit\nof background information we come from a',
                'of background information we come from a',
                'of background information we come from a\ncompany called le code from finland and']
    assert list(captions.get_caption_text(vtt_file1)) == expected

    expected = ['okay welcome to this session this is',
                'okay welcome to this session this is\ncalled the kinetic bunny need to meet',
                'called the kinetic bunny need to meet',
                'called the kinetic bunny need to meet\n'
                'the virtual bonnie emilio stop this is',
                'the virtual bonnie emilio stop this is',
                'the virtual bonnie emilio stop this is\n'
                'jana car who just to give a little bit',
                'jana car who just to give a little bit',
                'jana car who just to give a little bit\n'
                'of background information we come from a',
                'of background information we come from a',
                'of background information we come from a\n'
                'company called le code from finland and']
    assert list(captions.get_caption_text(srt_file3)) == expected


def test_get_unique_caption_lines(vtt_file1, srt_file3):
    expected = ['okay welcome to this session this is',
                'called the kinetic bunny need to meet',
                'the virtual bonnie emilio stop this is',
                'jana car who just to give a little bit',
                'of background information we come from a',
                'company called le code from finland and']
    assert list(captions.get_unique_caption_lines(vtt_file1)) == expected

    expected = ['okay welcome to this session this is',
                'called the kinetic bunny need to meet',
                'the virtual bonnie emilio stop this is',
                'jana car who just to give a little bit',
                'of background information we come from a',
                'company called le code from finland and']
    assert list(captions.get_unique_caption_lines(srt_file3)) == expected


EXPECTED_CAPTION_CHUNKS = [
    {'start_seconds': 5.269, 'text': 'okay welcome to this session this is'},
    {'start_seconds': 5.279, 'text': 'called the kinetic bunny need to meet'},
    {'start_seconds': 7.77, 'text': 'the virtual bonnie emilio stop this is'},
    {'start_seconds': 11.46, 'text': 'jana car who just to give a little bit'},
    {'start_seconds': 15.42, 'text': 'of background information we come from a'},
    {'start_seconds': 18.869, 'text': 'company called le code from finland and'},
]


@pytest.mark.parametrize('fixture_name', ['vtt_file1', 'srt_file3'])
def test_read_captions_with_timestamps(fixture_name, request):
    """read_captions_with_timestamps returns timestamped caption chunks with overlapping lines deduplicated."""
    caption_file = request.getfixturevalue(fixture_name)
    chunks = captions.read_captions_with_timestamps(caption_file)
    assert chunks == EXPECTED_CAPTION_CHUNKS
