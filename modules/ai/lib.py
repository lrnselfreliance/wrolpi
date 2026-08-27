"""Formatting helpers for the /api/ai blueprint — the LLM tool catalog.

Results are lean, flat JSON with server-computed links so the model never constructs URLs.
Links are relative to the WROLPi host (e.g. /videos/123); the caller (frontend, MCP client)
prefixes its own base URL.
"""
import pathlib
from typing import Optional

from bs4 import BeautifulSoup

from wrolpi.common import get_relative_to_media_directory, logger

logger = logger.getChild(__name__)

# Big content (captions, archive text, zim entries, help docs) is paged in chunks of this many
# characters, never silently truncated.  Sized for small (8k-token) model contexts.
PAGE_SIZE = 4_000
# Description length in a detail response; descriptions in search listings are shorter.
DETAIL_DESCRIPTION_LENGTH = 1_000
LISTING_DESCRIPTION_LENGTH = 300


def _relative_path(path) -> Optional[str]:
    """Return the media-relative string of a path from a FileGroup JSON dict, if possible."""
    if not path:
        return None
    try:
        return str(get_relative_to_media_directory(path))
    except Exception:
        return str(path)


def file_group_kind(fg: dict) -> str:
    """Categorize a FileGroup JSON dict for the model: video/archive/doc/image/file."""
    mimetype = fg.get('mimetype') or ''
    if fg.get('model') == 'video' or isinstance(fg.get('video'), dict):
        return 'video'
    if fg.get('model') == 'archive' or isinstance(fg.get('archive'), dict):
        return 'archive'
    if fg.get('model') == 'doc':
        return 'doc'
    if mimetype.startswith('image/'):
        return 'image'
    return 'file'


def wrolpi_link(fg: dict) -> Optional[str]:
    """Build the relative WROLPi UI link for a FileGroup JSON dict.

    Videos/docs/archives deep-link by FileGroup ID; epubs open in the reader; everything else is
    served directly from /media/ or /download/.
    """
    fg_id = fg.get('id')
    kind = file_group_kind(fg)
    if kind == 'video' and fg_id:
        return f'/videos/{fg_id}'
    if kind == 'doc' and fg_id:
        return f'/docs/{fg_id}'
    if kind == 'archive' and fg_id:
        return f'/archives/{fg_id}'

    mimetype = fg.get('mimetype') or ''
    primary_path = _relative_path(fg.get('primary_path'))
    if not primary_path:
        return None
    if mimetype.startswith('application/epub'):
        return f'/epub/epub.html?url=/download/{primary_path}'
    if mimetype.startswith('application/x-mobipocket-ebook'):
        return f'/download/{primary_path}'
    # Caddy serves any media file at /media/{path}.
    return f'/media/{primary_path}'


def _truncate(text: Optional[str], length: int) -> Optional[str]:
    if text and len(text) > length:
        return text[:length] + '…'
    return text


def format_file_group(fg: dict, description_length: int = LISTING_DESCRIPTION_LENGTH,
                      include_url: bool = False) -> dict:
    """Format a FileGroup JSON dict into the lean, flat shape the model consumes.

    Empty fields are omitted so results stay compact on small contexts.  The source URL is
    omitted unless requested (archive detail): given both, small models present the familiar
    external URL instead of the WROLPi link.
    """
    kind = file_group_kind(fg)
    result = dict(
        id=fg.get('id'),
        kind=kind,
        title=fg.get('title') or fg.get('name'),
        link=wrolpi_link(fg),
        mimetype=fg.get('mimetype'),
        size=fg.get('size'),
        published=fg.get('published_datetime'),
        author=fg.get('author'),
        tags=fg.get('tags') or None,
        url=fg.get('url') if include_url else None,
    )

    # FTS headline (content match context), if the search requested headlines.
    headline = fg.get('d_headline') or fg.get('b_headline') or fg.get('c_headline')
    if headline:
        result['headline'] = headline

    video = fg.get('video')
    if kind == 'video':
        result['duration'] = fg.get('length')
        result['captions_link'] = f'/api/ai/videos/{fg["id"]}/captions' if fg.get('id') else None
        if isinstance(video, dict):
            channel = video.get('channel')
            if isinstance(channel, dict):
                result['channel'] = channel.get('name') or channel.get('id')
            elif video.get('channel_id'):
                result['channel_id'] = video['channel_id']
            result['description'] = _truncate(video.get('description'), description_length)

    if kind == 'archive' and fg.get('id'):
        result['text_link'] = f'/api/ai/archives/{fg["id"]}/text'

    if kind == 'doc':
        doc = fg.get('doc') or {}
        result['subject'] = doc.get('subject')
        result['language'] = doc.get('language')
        result['pages'] = doc.get('page_count')
        result['description'] = _truncate(doc.get('description'), description_length)

    return {k: v for k, v in result.items() if v is not None}


def format_file_groups(file_groups: list, total: int, searched: bool = False) -> dict:
    """Format search results: lean items plus the total so the model narrows instead of paging."""
    result = dict(results=[format_file_group(i) for i in file_groups], total=total)
    if searched and total == 0:
        # Small models give up on one empty search; steer the retry.
        result['hint'] = ('No matches. Names may be spelled differently: try fewer or different'
                          ' words, list_collections for exact channel/domain names, or omit'
                          ' search_str to browse the newest items.')
    return result


def paginate_text(text: Optional[str], offset: int = 0) -> dict:
    """Page big content: ~PAGE_SIZE chars plus next_offset/total_chars, never silent truncation."""
    text = text or ''
    offset = max(int(offset or 0), 0)
    end = offset + PAGE_SIZE
    next_offset = end if end < len(text) else None
    return dict(content=text[offset:end], next_offset=next_offset, total_chars=len(text))


def html_to_text(html: str) -> str:
    """Strip HTML down to clean plain text for the model.  Pagination handles size."""
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()

    text = soup.get_text(separator='\n', strip=True)

    # Collapse multiple blank lines.
    lines = []
    prev_blank = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if not prev_blank:
                lines.append('')
            prev_blank = True
        else:
            lines.append(stripped)
            prev_blank = False
    return '\n'.join(lines)


def format_caption_chunks(chunks: Optional[list]) -> str:
    """Render caption chunks ({start_seconds, text}) as timestamped lines."""
    if not chunks:
        return ''
    lines = []
    for chunk in chunks:
        minutes, seconds = divmod(int(chunk.get('start_seconds') or 0), 60)
        hours, minutes = divmod(minutes, 60)
        lines.append(f'[{hours:02d}:{minutes:02d}:{seconds:02d}] {chunk.get("text") or ""}')
    return '\n'.join(lines)


def zim_entry_link(zim_id: int, path: str) -> str:
    return f'/api/zim/{zim_id}/entry/{path}'


def zim_metadata_dict(metadata) -> dict:
    """Zim lib functions return a ZimMetadata object; normalize it to a dict."""
    if metadata is None:
        return {}
    return metadata if isinstance(metadata, dict) else metadata.__json__()


def format_zim_search(zim_results: list) -> dict:
    """Flatten per-Zim search results into lean entries with links."""
    results = []
    total = 0
    for zim_result in zim_results:
        metadata = zim_metadata_dict(zim_result.get('metadata'))
        zim_title = metadata.get('title')
        total += zim_result.get('estimate') or 0
        for entry in zim_result.get('search') or []:
            zim_id = entry.get('zim_id')
            path = entry.get('path')
            result = dict(
                zim_id=zim_id,
                zim=zim_title,
                path=path,
                title=entry.get('title'),
                headline=entry.get('headline'),
                link=zim_entry_link(zim_id, path) if zim_id and path else None,
            )
            results.append({k: v for k, v in result.items() if v is not None})
    return dict(results=results, total=total)


def read_archive_text(archive) -> Optional[str]:
    """Return the readable plain text of an Archive: readability text, else stripped singlefile."""
    if (path := archive.readability_txt_path) and pathlib.Path(path).is_file():
        return pathlib.Path(path).read_text(errors='replace')
    if (path := archive.singlefile_path) and pathlib.Path(path).is_file():
        return html_to_text(pathlib.Path(path).read_text(errors='replace'))
    return None
