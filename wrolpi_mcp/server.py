"""WROLPi MCP Server — exposes WROLPi content to LLMs via the Model Context Protocol.

A thin proxy: every tool is one call to the WROLPi API's /api/ai blueprint, which owns (and
tests) the lean result shapes, links, and paging that used to live here.  External clients
(Claude etc.) and WROLPi's local assistant share that one behavior."""
import json
import logging
import sys

import httpx

from wrolpi_mcp.client import api_get, api_post
from wrolpi_mcp.config import API_BASE_URL, DEFAULT_LIMIT

from mcp.server.fastmcp import FastMCP

# All logging must go to stderr in stdio transport mode.
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("wrolpi_mcp")

mcp = FastMCP(
    "WROLPi",
    instructions=(
        "WROLPi is an offline digital library containing videos, archived web pages, "
        "ebooks, Zim encyclopedias (Wikipedia, etc.), maps, and documents. "
        "Use these tools to search and retrieve content from the library. "
        "IMPORTANT: When presenting results to the user, ALWAYS include the 'WROLPi Link' "
        "for every item. Never use the 'Source URL' — only use the local WROLPi Link. "
        "When calling tools, use the top-level ID (FileGroup ID)."
    ),
)

# ---------------------------------------------------------------------------
# Rendering helpers.  /api/ai returns lean flat JSON with relative links; these render it as
# text and prefix the WROLPi base URL.
# ---------------------------------------------------------------------------

# Big content (captions, page text, zim entries) is read page by page up to this many chars.
MAX_CONTENT_CHARS = 50_000

_FIELD_LABELS = (
    ('mimetype', 'Type'),
    ('size', 'Size'),
    ('duration', 'Duration'),
    ('published', 'Published'),
    ('channel', 'Channel'),
    ('has_captions', 'Has captions'),
    ('has_comments', 'Has comments'),
    ('author', 'Author'),
    ('subject', 'Subject'),
    ('language', 'Language'),
    ('pages', 'Pages'),
    ('url', 'Source URL'),
    ('headline', 'Headline'),
    ('description', 'Description'),
)

_KIND_HINTS = {
    'video': 'use this for get_file, read_content (captions/comments)',
    'archive': 'use this for get_file, read_content (page text)',
    'doc': 'use this for get_file',
}


def _link(relative: str | None) -> str | None:
    return f'{API_BASE_URL.rstrip("/")}{relative}' if relative else None


def _render_result(item: dict) -> str:
    """One lean /api/ai result as concise text.  The link goes first so the LLM can't drop it."""
    parts = []
    title = item.get('title')
    link = _link(item.get('link'))
    if title and link:
        parts.append(f'Title: {title}  —  LINK: {link}')
    elif title:
        parts.append(f'Title: {title}')
    elif link:
        parts.append(f'LINK: {link}')

    if item.get('id'):
        hint = _KIND_HINTS.get(item.get('kind'))
        parts.append(f'ID: {item["id"]}' + (f'  ({hint})' if hint else ''))
    for key, label in _FIELD_LABELS:
        if value := item.get(key):
            parts.append(f'{label}: {value}')
    if tags := item.get('tags'):
        parts.append(f'Tags: {", ".join(map(str, tags))}')
    if history := item.get('history'):
        parts.append(f'Earlier snapshots ({len(history)}):')
        for snapshot in history:
            parts.append(f'  - {snapshot.get("title", "Untitled")} (ID: {snapshot.get("id")}, {snapshot.get("published", "?")})')
    return '\n'.join(parts)


def _render_results(data: dict) -> str:
    results = data.get('results') or []
    if not results:
        return 'No results found.'
    sections = [f'--- Result {i} ---\n{_render_result(item)}' for i, item in enumerate(results, 1)]
    text = '\n\n'.join(sections)
    if (total := data.get('total')) is not None:
        text += f'\n\nTotal matching: {total}'
    if matches := data.get('matches'):
        text += '\n\nNames matching the term (use to narrow the search):'
        for channel in matches.get('channels') or []:
            text += f"\n  channel: {channel.get('name')} (ID: {channel.get('id')})"
        for group in ('domains', 'authors', 'subjects'):
            for item in matches.get(group) or []:
                text += f"\n  {group[:-1]}: {item.get('name')}"
    return text


async def _read_paged(path: str, params: dict | None = None, max_chars: int = MAX_CONTENT_CHARS) -> str:
    """Read a paged /api/ai text endpoint until it ends or max_chars is reached."""
    params = dict(params or {})
    chunks = []
    read = 0
    offset = 0
    while True:
        data = await api_get(path, params={**params, 'offset': offset})
        chunks.append(data.get('content') or '')
        read += len(chunks[-1])
        offset = data.get('next_offset')
        if offset is None or read >= max_chars:
            break
    text = ''.join(chunks)
    if offset is not None:
        text += '\n\n[Truncated]'
    return text


def _render_zim_entries(data: dict) -> str:
    results = data.get('results') or []
    if not results:
        return 'No results found.'
    sections = []
    for i, entry in enumerate(results, 1):
        parts = [f'--- Result {i} ---']
        title = entry.get('title')
        link = _link(entry.get('link'))
        if title and link:
            parts.append(f'Title: {title}  —  LINK: {link}')
        elif title:
            parts.append(f'Title: {title}')
        if entry.get('zim'):
            parts.append(f'Zim: {entry["zim"]}')
        if entry.get('zim_id') is not None:
            parts.append(f'Zim ID: {entry["zim_id"]} | Path: {entry.get("path", "")}')
        if entry.get('headline'):
            parts.append(f'Headline: {entry["headline"]}')
        sections.append('\n'.join(parts))
    text = '\n\n'.join(sections)
    if (total := data.get('total')) is not None:
        text += f'\n\nTotal matching: {total}'
    return text


# ---------------------------------------------------------------------------
# Search tools
# ---------------------------------------------------------------------------

@mcp.tool(annotations={"readOnlyHint": True})
async def search(
    query: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    mimetypes: list[str] | None = None,
    tag_names: list[str] | None = None,
) -> str:
    """Search all WROLPi content (videos, archives, ebooks, and other files).

    Args:
        query: Text to search for across titles, content, and metadata.
        limit: Maximum number of results to return.
        offset: Number of results to skip (for pagination).
        mimetypes: Filter by MIME types, e.g. ["video/mp4", "text/html"].
        tag_names: Filter by tag names.
    """
    body = {"search_str": query, "limit": limit, "offset": offset}
    if tag_names:
        body["tag_names"] = tag_names
    # mimetypes are no longer a filter; a kind is.  Map the common prefixes.
    if mimetypes:
        kinds = {("video" if m.startswith("video/") else "archive" if m == "text/html" else "doc") for m in mimetypes}
        if len(kinds) == 1:
            body["kind"] = kinds.pop()
    return _render_results(await api_post("/api/ai/files/search", json=body))


@mcp.tool(annotations={"readOnlyHint": True})
async def search_videos(
    query: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    channel_id: int | None = None,
    tag_names: list[str] | None = None,
) -> str:
    """Search downloaded videos by title and captions.

    Args:
        query: Text to search for in video titles and captions.
        limit: Maximum number of results.
        offset: Pagination offset.
        channel_id: Filter to a specific channel by ID.
        tag_names: Filter by tag names.
    """
    body = {"search_str": query, "limit": limit, "offset": offset, "kind": "video"}
    if channel_id is not None:
        body["channel"] = str(channel_id)
    if tag_names:
        body["tag_names"] = tag_names
    return _render_results(await api_post("/api/ai/files/search", json=body))


@mcp.tool(annotations={"readOnlyHint": True})
async def search_archives(
    query: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    domain: str | None = None,
    tag_names: list[str] | None = None,
) -> str:
    """Search archived web pages (saved with SingleFile).

    Args:
        query: Text to search for in archived page titles and content.
        limit: Maximum number of results.
        offset: Pagination offset.
        domain: Filter to a specific domain (e.g. "example.com").
        tag_names: Filter by tag names.
    """
    body = {"search_str": query, "limit": limit, "offset": offset, "kind": "archive"}
    if domain:
        body["domain"] = domain
    if tag_names:
        body["tag_names"] = tag_names
    return _render_results(await api_post("/api/ai/files/search", json=body))


@mcp.tool(annotations={"readOnlyHint": True})
async def search_docs(
    query: str | None = None,
    author: str | None = None,
    subject: str | None = None,
    language: str | None = None,
    mimetype: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    tag_names: list[str] | None = None,
) -> str:
    """Search documents (ebooks, PDFs, comics, office docs) in the library.

    At least one of query, author, subject, or tag_names should be provided.

    Args:
        query: Text to search for in document titles and content.
        author: Filter by author name (partial match).
        subject: Filter by subject (partial match).
        language: Filter by language code (exact match, e.g. "en").
        mimetype: Filter by MIME type prefix (e.g. "application/epub", "application/pdf").
        limit: Maximum number of results.
        offset: Pagination offset.
        tag_names: Filter by tag names.
    """
    body = {"limit": limit, "offset": offset, "kind": "doc"}
    if query:
        body["search_str"] = query
    if author:
        body["author"] = author
    if subject:
        body["subject"] = subject
    if tag_names:
        body["tag_names"] = tag_names
    # language and mimetype are accepted for compatibility; the consolidated search does not filter on them.
    return _render_results(await api_post("/api/ai/files/search", json=body))


@mcp.tool(annotations={"readOnlyHint": True})
async def get_doc(file_group_id: int) -> str:
    """Get detailed information about a specific document (ebook, PDF, comic, etc.).

    Args:
        file_group_id: The top-level ID from search results (this is the FileGroup ID).
    """
    return _render_result(await api_get(f"/api/ai/files/{file_group_id}"))


@mcp.tool(annotations={"readOnlyHint": True})
async def search_zim(
    zim_id: int,
    query: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Search within a Zim encyclopedia (e.g. Wikipedia, Wiktionary).

    Use list_zim_files first to find the zim_id.

    Args:
        zim_id: ID of the Zim file to search.
        query: Text to search for.
        limit: Maximum number of results.
        offset: Pagination offset.
    """
    body = {"search_str": query, "zim_id": zim_id, "limit": limit, "offset": offset}
    try:
        data = await api_post("/api/ai/zims/search", json=body)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Zim ID {zim_id} not found. Use list_zim_files to find valid Zim IDs."
        raise
    return _render_zim_entries(data)


@mcp.tool(annotations={"readOnlyHint": True})
async def search_default_zims(
    query: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Search only the Zim encyclopedias that have 'search by default' enabled.

    This does NOT search all Zim files. To search a specific Zim, use list_zim_files
    to find its ID, then use search_zim.

    Args:
        query: Text to search for.
        limit: Maximum results per Zim file.
        offset: Pagination offset.
    """
    body = {"search_str": query, "limit": limit, "offset": offset}
    return _render_zim_entries(await api_post("/api/ai/zims/search", json=body))


# ---------------------------------------------------------------------------
# Content retrieval tools
# ---------------------------------------------------------------------------

@mcp.tool(annotations={"readOnlyHint": True})
async def get_video(file_group_id: int) -> str:
    """Get detailed information about a specific video.

    Args:
        file_group_id: The FileGroup ID from search results.
    """
    return _render_result(await api_get(f"/api/ai/files/{file_group_id}"))


@mcp.tool(annotations={"readOnlyHint": True})
async def get_video_captions(file_group_id: int) -> str:
    """Get the subtitle/caption text of a video. Useful for understanding video content without watching.

    Args:
        file_group_id: The FileGroup ID from search results.
    """
    text = await _read_paged(f"/api/ai/files/{file_group_id}/content", params={"part": "text"})
    return text or "No captions available for this video."


@mcp.tool(annotations={"readOnlyHint": True})
async def get_video_comments(file_group_id: int) -> str:
    """Get comments/discussion for a video.

    Args:
        file_group_id: The FileGroup ID from search results.
    """
    text = await _read_paged(f"/api/ai/files/{file_group_id}/content", params={"part": "comments"})
    return text or "No comments available for this video."


@mcp.tool(annotations={"readOnlyHint": True})
async def get_archive(file_group_id: int) -> str:
    """Get details about an archived web page, including its history of snapshots.

    Args:
        file_group_id: The FileGroup ID from search results.
    """
    return _render_result(await api_get(f"/api/ai/files/{file_group_id}"))


@mcp.tool(annotations={"readOnlyHint": True})
async def get_archive_text(file_group_id: int) -> str:
    """Get the readable plain text content of an archived web page.

    This returns the Readability-extracted text, which is clean and suitable for reading.

    Args:
        file_group_id: The FileGroup ID from search results.
    """
    try:
        text = await _read_paged(f"/api/ai/files/{file_group_id}/content", params={"part": "text"})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Could not retrieve text content for archive {file_group_id}. Try get_archive for metadata."
        raise
    return text


@mcp.tool(annotations={"readOnlyHint": True})
async def get_zim_entry(zim_id: int, entry_path: str) -> str:
    """Read a specific article/entry from a Zim file (e.g. a Wikipedia article).

    Use search_zim first to find entry paths.

    Args:
        zim_id: ID of the Zim file.
        entry_path: Path to the entry within the Zim file (from search results).
    """
    try:
        first = await api_get(f"/api/ai/zims/{zim_id}/entry", params={"path": entry_path})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Zim ID {zim_id} not found. Use list_zim_files to find valid Zim IDs."
        raise
    text = first.get("content") or ""
    if first.get("next_offset") is not None:
        text += await _read_paged(f"/api/ai/zims/{zim_id}/entry",
                                  params={"path": entry_path, "offset": first["next_offset"]},
                                  max_chars=MAX_CONTENT_CHARS - len(text))
    link = _link(first.get("link"))
    return f"LINK: {link}\n\n{text}"


# ---------------------------------------------------------------------------
# Kind-generic tools (the compact set the built-in assistant uses)
# ---------------------------------------------------------------------------

@mcp.tool(annotations={"readOnlyHint": True})
async def search_files(
    query: str | None = None,
    kind: str | None = None,
    channel: str | None = None,
    domain: str | None = None,
    author: str | None = None,
    subject: str | None = None,
    tag_names: list[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Search the whole library (videos, archived web pages, documents/ebooks) in one call.

    Args:
        query: Text to search for in titles and content.  Omit to browse the newest items.
        kind: Narrow to "video", "archive", or "doc".
        channel: A video channel name (or id); implies kind=video.
        domain: An archived site name, e.g. "example.com"; implies kind=archive.
        author: Document author (partial match); implies kind=doc.
        subject: Document subject (partial match); implies kind=doc.
        tag_names: Only items with these tags.
        limit: Maximum results.
        offset: Pagination offset.
    """
    body = {k: v for k, v in dict(search_str=query, kind=kind, channel=channel, domain=domain, author=author,
                                  subject=subject, tag_names=tag_names, limit=limit, offset=offset).items()
            if v not in (None, [], "")}
    return _render_results(await api_post("/api/ai/files/search", json=body))


@mcp.tool(annotations={"readOnlyHint": True})
async def get_file(file_group_id: int) -> str:
    """Get details about one item of any kind (video, archived page, document) by its ID from search results."""
    return _render_result(await api_get(f"/api/ai/files/{file_group_id}"))


@mcp.tool(annotations={"readOnlyHint": True})
async def read_content(file_group_id: int, part: str = "text") -> str:
    """Read what an item says: a video's captions or an archived page's text (part="text"), or a video's
    comments (part="comments").

    Args:
        file_group_id: The ID from search results.
        part: "text" (default) or "comments".
    """
    try:
        text = await _read_paged(f"/api/ai/files/{file_group_id}/content", params={"part": part})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"No {part} available for item {file_group_id}. Try get_file for its details."
        raise
    return text or f"No {part} available for item {file_group_id}."


# ---------------------------------------------------------------------------
# Browsing / listing tools
# ---------------------------------------------------------------------------

@mcp.tool(annotations={"readOnlyHint": True})
async def list_collections(kind: str | None = None) -> str:
    """List all collections (channels, domains, etc.) in the library.

    Args:
        kind: Filter by collection kind: "channel", "domain", or None for all.
    """
    params = {"kind": kind} if kind else None
    data = await api_get("/api/ai/collections", params=params)
    collections = data.get("results") or []
    if not collections:
        return "No collections found."
    lines = []
    for collection in collections:
        parts = [f"ID: {collection.get('id')} | {collection.get('name', 'Unnamed')} ({collection.get('kind', '?')})"]
        if collection.get("directory"):
            parts.append(f"  Directory: {collection['directory']}")
        lines.append("\n".join(parts))
    lines.append(f"\nTotal: {data.get('total', len(collections))}")
    return "\n\n".join(lines)


@mcp.tool(annotations={"readOnlyHint": True})
async def list_files(path: str = "", offset: int = 0) -> str:
    """List the directories and files inside one directory of the WROLPi media directory.

    Use this to explore how the library is organized on disk (e.g. "videos/", "archive/", a channel's
    directory).  Directories are listed first, then files.  Every entry's relative path can be passed
    back to list_files to descend.  Large directories are paged; call again with the returned offset.

    Args:
        path: Directory relative to the media directory (e.g. "videos/SomeChannel").  Empty for the top level.
        offset: Number of entries to skip (from a previous listing's "next offset").
    """
    try:
        data = await api_get("/api/ai/files/list", params={"path": path, "offset": offset})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"No such directory: {path or '/'}"
        raise
    lines = [f"Directory: {data.get('path') or '/'}"]
    for directory in data.get("directories") or []:
        lines.append(f"  [dir]  {directory['path']}")
    for file in data.get("files") or []:
        size = file.get("size")
        size_text = f"{size / (1024 * 1024):,.1f} MB" if size and size >= 1024 * 1024 else f"{size or 0:,} B"
        mimetype = file.get("mimetype") or "unknown"
        lines.append(f"  [file] {file['path']}  ({mimetype}, {size_text})")
    if not (data.get("directories") or data.get("files")):
        lines.append("  (empty)")
    lines.append(f"\nTotal entries: {data.get('total', 0)}")
    if (next_offset := data.get("next_offset")) is not None:
        lines.append(f"More entries available: call list_files again with offset={next_offset}")
    return "\n".join(lines)


@mcp.tool(annotations={"readOnlyHint": True})
async def list_zim_files() -> str:
    """List all available Zim encyclopedias (Wikipedia, Wiktionary, etc.).

    Returns Zim IDs needed for search_zim and get_zim_entry.
    """
    data = await api_get("/api/ai/zims")
    zims = data.get("results") or []
    if not zims:
        return "No Zim files found."
    lines = []
    for zim in zims:
        size_mb = (zim.get("size") or 0) / (1024 * 1024)
        parts = [
            f"ID: {zim.get('id')} | {zim.get('title', 'Unknown')}",
            f"  Creator: {zim.get('creator', 'Unknown')}",
            f"  Description: {zim.get('description', 'N/A')}",
            f"  Size: {size_mb:,.0f} MB",
        ]
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


@mcp.tool(annotations={"readOnlyHint": True})
async def list_tags() -> str:
    """List every tag in the library with how many files, Zim entries, channels, and domains carry it.

    Tag names can be passed as tag_names to the search tools.  Users tag what they care about, so this
    is a good map of their interests.  Also returns the most recently used tag names.
    """
    data = await api_get("/api/ai/tags")
    results = data.get("results") or []
    if not results:
        return "No tags found."
    lines = []
    for tag in results:
        counts = ", ".join(f"{tag.get(k, 0)} {k.replace('_', ' ')}" for k in
                           ("file_groups", "zim_entries", "channels", "domains") if tag.get(k))
        lines.append(f"  {tag['name']}" + (f"  ({counts})" if counts else "  (unused)"))
    text = f"Tags ({data.get('total', len(results))}):\n" + "\n".join(lines)
    if recent := data.get("recent"):
        text += f"\n\nRecently used: {', '.join(recent)}"
    return text


@mcp.tool(annotations={"readOnlyHint": True})
async def search_suggestions(query: str, tag_names: list[str] | None = None) -> str:
    """Preview what a search would find before running it.

    Returns the channels, domains (archived sites), authors, and subjects whose names match the query,
    and estimates of how many files and Zim entries the search would return.  Use the channel ID with
    search_videos, the domain with search_archives, the author/subject with search_docs.

    Args:
        query: The term the user wants to search for.
        tag_names: Narrow the file estimate to items with these tags.
    """
    body = {"search_str": query}
    if tag_names:
        body["tag_names"] = tag_names
    data = await api_post("/api/ai/search/suggestions", json=body)
    lines = []
    for channel in data.get("channels") or []:
        lines.append(f"  Channel: {channel['name']}  (ID: {channel['id']})  LINK: {_link(channel.get('link'))}")
    for domain in data.get("domains") or []:
        lines.append(f"  Domain: {domain['name']}")
    for author in data.get("authors") or []:
        lines.append(f"  Author: {author['name']}")
    for subject in data.get("subjects") or []:
        lines.append(f"  Subject: {subject['name']}")
    if not lines:
        lines.append("  No matching channels, domains, authors, or subjects.")
    estimates = data.get("estimates") or {}
    lines.append(f"\nEstimated matching files: {estimates.get('file_groups', 0)}"
                 f" (deep content search: {estimates.get('file_groups_deep', 0)})")
    for zim in estimates.get("zims") or []:
        lines.append(f"  Zim '{zim.get('title')}' (ID {zim.get('id')}): ~{zim.get('estimate', 0)} entries")
    return "\n".join(lines)


@mcp.tool(annotations={"readOnlyHint": True})
async def list_downloads(status: str | None = None, limit: int = DEFAULT_LIMIT) -> str:
    """Read the WROLPi download queue: summary, recurring downloads (channels, feeds), and one-time downloads.

    Use this when the user asks what is downloading, what failed and why, or what is scheduled.
    Downloads cannot be started, stopped, or retried from here.

    Args:
        status: Only show downloads with this status: new, pending, failed, deferred, or complete.
        limit: Maximum recurring and one-time downloads to show (each).
    """
    params = {"limit": limit}
    if status:
        params["status"] = status
    data = await api_get("/api/ai/downloads", params=params)
    summary = data.get("summary") or {}
    lines = ["Summary: " + ", ".join(f"{k}={v}" for k, v in summary.items())]

    def render(download: dict) -> str:
        parts = [f"  [{download.get('status')}] {download.get('url')}  (ID: {download.get('id')},"
                 f" {download.get('downloader')})"]
        if download.get("frequency"):
            parts.append(f"      every {download['frequency']}s, next: {download.get('next_download') or 'unscheduled'}")
        if download.get("destination"):
            parts.append(f"      destination: {download['destination']}")
        if download.get("tag_names"):
            parts.append(f"      tags: {', '.join(download['tag_names'])}")
        if download.get("error"):
            parts.append(f"      error: {download['error']}")
        return "\n".join(parts)

    recurring = data.get("recurring") or []
    once = data.get("once") or []
    lines.append(f"\nRecurring downloads ({len(recurring)} shown):")
    lines.extend(render(i) for i in recurring) if recurring else lines.append("  none")
    lines.append(f"\nOne-time downloads ({len(once)} shown, {data.get('pending_once', 0)} pending):")
    lines.extend(render(i) for i in once) if once else lines.append("  none")
    return "\n".join(lines)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_map_overview() -> str:
    """Describe the maps on this WROLPi: downloaded map regions, whether each has a place-search index,
    subscribed regions, and the user's saved pins (with links)."""
    data = await api_get("/api/ai/map")
    lines = ["Map files:"]
    files = data.get("files") or []
    for file in files:
        size_gb = (file.get("size") or 0) / (1024 ** 3)
        index = "searchable" if file.get("has_search_index") else "no search index"
        lines.append(f"  {file['name']}  ({size_gb:,.2f} GB, {index})")
    if not files:
        lines.append("  none")
    subscriptions = data.get("subscriptions") or []
    names = [i.get("name") or i.get("region") if isinstance(i, dict) else str(i) for i in subscriptions]
    lines.append(f"\nSubscribed regions: {', '.join(names) if names else 'none'}")
    lines.append("\nPins:")
    pins = data.get("pins") or []
    for pin in pins:
        lines.append(f"  {pin.get('label') or 'Unlabeled'}  ({pin.get('lat')}, {pin.get('lon')})"
                     f"  LINK: {_link(pin.get('link'))}")
    if not pins:
        lines.append("  none")
    return "\n".join(lines)


@mcp.tool(annotations={"readOnlyHint": True})
async def search_places(
    query: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    lat: float | None = None,
    lon: float | None = None,
) -> str:
    """Find towns, cities, and landmarks by name in the downloaded maps.  Each result links to the WROLPi map.

    Args:
        query: Place name (prefix match), e.g. "Portland".
        limit: Maximum results.
        offset: Pagination offset.
        lat: Latitude to rank nearby places first.
        lon: Longitude to rank nearby places first.
    """
    params = {"q": query, "limit": limit, "offset": offset}
    if lat is not None and lon is not None:
        params.update(lat=lat, lon=lon)
    data = await api_get("/api/ai/map/search", params=params)
    results = data.get("results") or []
    if not results:
        return "No places found. The maps may have no search index (see get_map_overview)."
    lines = []
    for i, place in enumerate(results, 1):
        detail = ", ".join(str(place[k]) for k in ("kind", "region") if place.get(k))
        if place.get("population"):
            detail += f", pop. {place['population']:,}"
        lines.append(f"{i}. {place['name']}  ({detail})  at {place.get('lat')}, {place.get('lon')}"
                     f"  LINK: {_link(place.get('link'))}")
    lines.append(f"\nTotal matching: {data.get('total', len(results))}")
    return "\n".join(lines)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_statistics() -> str:
    """Get an overview of what content is stored in the WROLPi library.

    Returns counts and sizes for videos, archives, ebooks, Zim files, and other content.
    """
    data = await api_get("/api/statistics")
    return json.dumps(data, indent=2, default=str)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_inventory() -> str:
    """List all inventories (emergency supplies, food storage, etc.)."""
    data = await api_get("/api/ai/inventories")
    inventories = data.get("results") or []
    if not inventories:
        return "No inventories found."
    lines = []
    for inventory in inventories:
        parts = [f"Slug: {inventory.get('slug')} | {inventory.get('name', 'Unnamed')}"]
        if inventory.get("item_count") is not None:
            parts.append(f"  Items: {inventory['item_count']}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_inventory_items(inventory_slug: str) -> str:
    """Get all items in a specific inventory.

    Args:
        inventory_slug: The inventory slug (from get_inventory results).
    """
    data = await api_get("/api/ai/inventories", params={"slug": inventory_slug})
    return json.dumps(data, indent=2, default=str)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_status() -> str:
    """Get WROLPi system status (version, services, CPU, disks, flags)."""
    data = await api_get("/api/ai/status")
    return json.dumps(data, indent=2, default=str)
