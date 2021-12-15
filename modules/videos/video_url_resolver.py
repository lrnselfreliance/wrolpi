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

    try:
        formatter = formatters[domain]
        return formatter(entry)
    except KeyError:
        # Unable to resolve, try the URL as is.
        return entry['url']
