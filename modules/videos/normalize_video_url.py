import re
import urllib.parse

from wrolpi.common import logger

logger = logger.getChild(__name__)

YOUTUBE_SHORT_REGEX = re.compile(r'https?://w{3}?\.?youtube.com/shorts/([-,._0-9a-zA-Z]{5,15})')
YOUTU_BE_REGEX = re.compile(r'https?://(?:w{3}\.)?youtu\.be/([-,._0-9a-zA-Z]{5,15})')


def strip_extra_from_url(url: str) -> str:
    """Remove any query parameters which are unnecessary for a video url."""
    if url.startswith('https://www.youtube.com/') and 'watch?' in url:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        if 'v' in query and ('list' in query or 'si' in query or 'pp' in query):
            # Remove `list` or `si` from video URL.
            v, = query['v']
            url = f'https://www.youtube.com/watch?v={v}'
    return url


# TODO Move this to a global location.  We want an Archive's URL to match a Video's URL.

def normalize_video_url(url: str) -> str:
    """Convert video URLs to what is expected to be in the yt-dlp info json."""
    url = url.strip()
    if (match := YOUTUBE_SHORT_REGEX.match(url)) or (match := YOUTU_BE_REGEX.match(url)):
        source_id = match.group(1)
        url = f'https://www.youtube.com/watch?v={source_id}'
    url = strip_extra_from_url(url)
    return url
