from modules.videos.models import Channel, ChannelDownload
from wrolpi.downloader import Download


def migrate_channel_downloads(session):
    channels_by_url = {i.url: i for i in session.query(Channel).all()}
    downloads = session.query(Download).all()
    need_commit = False
    for download in downloads:
        channel = channels_by_url.get(download.url)
        if channel:
            cd = session.query(ChannelDownload).filter_by(download_url=download.url).one_or_none()
            if not cd:
                cd = ChannelDownload(channel_id=channel.id, download_url=download.url)
                session.add(cd)
                need_commit = True

    for download in downloads:
        destination = download.settings.get('destination') if download.settings else None
        if not destination:
            continue

        channel = session.query(Channel).filter_by(directory=destination).one_or_none()
        if channel:
            cd = session.query(ChannelDownload).filter_by(download_url=download.url).one_or_none()
            if not cd:
                cd = ChannelDownload(channel_id=channel.id, download_url=download.url)
                session.add(cd)
                need_commit = True

    if need_commit:
        session.commit()
