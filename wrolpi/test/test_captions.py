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


def test_strip_youtube_caption_positioning(vtt_file1):
    """YouTube's `align:start position:0%` cue settings are removed so captions render centered."""
    original = vtt_file1.read_text()
    assert 'align:start position:0%' in original

    changed = captions.strip_youtube_caption_positioning(vtt_file1)
    assert changed is True

    new_text = vtt_file1.read_text()
    # The mis-positioning cue settings are gone...
    assert 'align:start position:0%' not in new_text
    # ...but the timestamps and the `<c>` word-timing tags in the cue text survive untouched.
    assert '00:00:00.000 --> 00:00:05.269' in new_text
    assert '<00:00:01.310><c> welcome</c>' in new_text
    # The captions are still readable/parseable and unchanged in content.
    assert list(captions.read_captions_with_timestamps(vtt_file1)) == EXPECTED_CAPTION_CHUNKS

    # Idempotent: a second pass changes nothing.
    assert captions.strip_youtube_caption_positioning(vtt_file1) is False
    assert vtt_file1.read_text() == new_text


def test_strip_youtube_caption_positioning_leaves_clean_files(vtt_file2):
    """A VTT with no cue settings (already centered) is not rewritten."""
    original = vtt_file2.read_text()
    assert 'align:start position:0%' not in original

    assert captions.strip_youtube_caption_positioning(vtt_file2) is False
    assert vtt_file2.read_text() == original


def test_strip_youtube_caption_positioning_preserves_deliberate_placement(test_directory):
    """A cue deliberately positioned (with a `line` setting) is not the auto-caption signature; leave it."""
    vtt = test_directory / 'deliberate.en.vtt'
    content = (
        'WEBVTT\n'
        '\n'
        '00:00:00.000 --> 00:00:02.000 align:start position:0% line:0\n'
        'top-left on purpose\n'
        '\n'
        '00:00:02.000 --> 00:00:04.000 align:start position:0%\n'
        'auto-caption line\n'
    )
    vtt.write_text(content)

    changed = captions.strip_youtube_caption_positioning(vtt)
    assert changed is True

    new_text = vtt.read_text()
    # The deliberate `line:0` cue is untouched...
    assert '00:00:00.000 --> 00:00:02.000 align:start position:0% line:0' in new_text
    # ...while the plain auto-caption cue is centered.
    assert '00:00:02.000 --> 00:00:04.000\nauto-caption line' in new_text
