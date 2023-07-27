import pytest


@pytest.mark.asyncio()
async def test_ffprobe_stream_methods(simple_video):
    """ffprobe data can be used to get data about specific streams in the video file."""
    assert await simple_video.get_ffprobe_json()

    assert simple_video.get_streams_by_codec_type('video')
    assert simple_video.get_streams_by_codec_type('audio')
    assert simple_video.get_streams_by_codec_type('subtitle')

    assert simple_video.get_streams_by_codec_name('h264')
    assert simple_video.get_streams_by_codec_name('aac')
    assert simple_video.get_streams_by_codec_name('mov_text')
