import re

from wrolpi.common import logger

logger = logger.getChild(__name__)

formatters = {
    'youtube.com': lambda i: f'https://youtube.com/watch?v={i["url"]}',
    'www.youtube.com': lambda i: f'https://youtube.com/watch?v={i["url"]}',
}


def video_url_resolver(domain: str, entry: dict) -> str:
    """
    Guess the full URL of a Youtube-DL entry.
    """
    if 'webpage_url' in entry:
        return entry['webpage_url']

    if entry.get('url', '').startswith('https://'):
        return entry['url']
    if entry.get('url', '').startswith('http://'):
        return entry['url']

    try:
        formatter = formatters[domain]
        return formatter(entry)
    except KeyError:
        # Unable to resolve, try the URL as is.
        return entry['url']


YOUTUBE_SHORT_REGEX = re.compile(r'https?:\/\/w{3}?\.?youtube.com\/shorts\/(.{5,15})')


def normalize_youtube_shorts_url(url: str) -> str:
    """Convert a YouTube "shorts" URL to a regular video URL.

    This is to avoid downloading shorts twice."""
    if match := YOUTUBE_SHORT_REGEX.match(url.strip()):
        source_id = match.group(1)
        return f'https://www.youtube.com/watch?v={source_id}'
    return url
