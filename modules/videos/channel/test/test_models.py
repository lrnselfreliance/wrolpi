def test_delete_channel_no_url(test_session, test_client, channel_factory):
    """
    A Channel can be deleted even if it has no URL.
    """
    channel = channel_factory()
    channel.url = None
    test_session.commit()

    channel.delete_with_videos()
