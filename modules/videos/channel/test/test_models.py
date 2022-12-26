import pytest


def test_delete_channel_no_url(test_session, test_client, channel_factory):
    """
    A Channel can be deleted even if it has no URL.
    """
    channel = channel_factory()
    channel.url = None
    test_session.commit()

    channel.delete_with_videos()


@pytest.mark.asyncio
async def test_channel_refresh_censored(test_session, channel_factory, video_factory):
    """Censored videos are discovered when refreshing a channel's directory."""
    channel = channel_factory()
    channel.info_json = {
        'entries': [
            {'id': 'one', 'view_count': 100},
            {'id': 'two', 'view_count': 200},
            # Three was deleted, it should be marked as censored.
            # {'id': 'three', 'view_count': 300},
        ]
    }
    vid1 = video_factory(channel_id=channel.id, source_id='one')
    vid2 = video_factory(channel_id=channel.id, source_id='two')
    vid3 = video_factory(channel_id=channel.id, source_id='three')
    test_session.commit()

    assert vid1.censored is False and vid1.view_count is None
    assert vid2.censored is False and vid1.view_count is None
    assert vid3.censored is False and vid1.view_count is None

    await channel.refresh_files()

    assert vid1.censored is False and vid1.view_count == 100
    assert vid2.censored is False and vid2.view_count == 200
    assert vid3.censored is True and vid3.view_count is None
