from modules.videos import downloader
from wrolpi import before_startup


@before_startup
def startup_spread_channel_downloads():
    from .channel import lib as channel_lib
    channel_lib.spread_channel_downloads()
