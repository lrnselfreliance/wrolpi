"""In-memory search over the WROLPi help markdown.

The help docs are a small corpus (dozens of markdown files) served by mkdocs from the wrolpi-help
repository.  They live outside the media directory and get no FileGroups, so they are searched
in-process: files are parsed on demand and cached by mtime.  No database, no index to build.
"""
import dataclasses
import os
import pathlib
import re
from typing import Dict, List, Optional

from wrolpi.common import logger
from wrolpi.vars import PROJECT_DIR

logger = logger.getChild(__name__)

# Native installs clone wrolpi-help to /opt/wrolpi-help; development uses the git submodule.
# The docker api container gets a read-only bind mount at the native location.
DEFAULT_HELP_DIRS = (
    pathlib.Path('/opt/wrolpi-help/docs'),
    PROJECT_DIR / 'docker/help/wrolpi-help/docs',
)

SNIPPET_LENGTH = 200


def get_help_docs_directory() -> Optional[pathlib.Path]:
    """The directory containing the help markdown, or None when help is not installed."""
    if directory := os.environ.get('HELP_DOCS_DIR'):
        directory = pathlib.Path(directory)
        return directory if directory.is_dir() else None
    for directory in DEFAULT_HELP_DIRS:
        if directory.is_dir():
            return directory
    return None


@dataclasses.dataclass
class HelpDoc:
    slug: str  # relative path without .md, e.g. "system/logs"
    title: str
    headings: List[str]
    body: str
    mtime: float


# slug -> HelpDoc, invalidated per-file by mtime.
_CACHE: Dict[str, HelpDoc] = {}


def _parse_doc(slug: str, path: pathlib.Path) -> HelpDoc:
    body = path.read_text(errors='replace')
    title = None
    headings = []
    for line in body.splitlines():
        if match := re.match(r'^(#{1,6})\s+(.+)', line):
            heading = match.group(2).strip()
            headings.append(heading)
            if title is None and match.group(1) == '#':
                title = heading
    return HelpDoc(slug=slug, title=title or slug, headings=headings, body=body, mtime=path.stat().st_mtime)


def load_help_docs() -> List[HelpDoc]:
    """Load every help markdown file, reusing cached parses of unchanged files."""
    directory = get_help_docs_directory()
    if not directory or not directory.is_dir():
        return []

    docs = []
    seen = set()
    for path in sorted(directory.rglob('*.md')):
        slug = str(path.relative_to(directory)).removesuffix('.md')
        seen.add(slug)
        try:
            cached = _CACHE.get(slug)
            if not cached or cached.mtime != path.stat().st_mtime:
                _CACHE[slug] = _parse_doc(slug, path)
            docs.append(_CACHE[slug])
        except OSError as e:
            logger.warning(f'Could not read help doc {path}', exc_info=e)
    # Drop deleted files from the cache.
    for slug in set(_CACHE) - seen:
        del _CACHE[slug]
    return docs


def help_doc_link(slug: str) -> str:
    """The mkdocs URL path of a doc; the help server (port 8086) serves index.md at /."""
    if slug == 'index':
        return '/'
    slug = slug.removesuffix('/index')
    return f'/{slug}/'


def _tokenize(text: str) -> List[str]:
    return [i for i in re.split(r'\W+', text.lower()) if len(i) >= 2]


def _snippet(body: str, tokens: List[str]) -> Optional[str]:
    """A little context around the first token match in the body."""
    lower = body.lower()
    position = min((p for token in tokens if (p := lower.find(token)) >= 0), default=-1)
    if position < 0:
        return None
    start = max(position - SNIPPET_LENGTH // 4, 0)
    snippet = body[start:start + SNIPPET_LENGTH]
    snippet = re.sub(r'\s+', ' ', snippet).strip()
    return f'…{snippet}…'


def search_help(search_str: str, limit: int = 5) -> (List[dict], int):
    """Score every help doc against the query; title matches beat heading matches beat body matches."""
    tokens = _tokenize(search_str or '')
    if not tokens:
        return []

    scored = []
    for doc in load_help_docs():
        title = doc.title.lower()
        headings = ' '.join(doc.headings).lower()
        body = doc.body.lower()
        score = 0
        for token in tokens:
            score += 10 * title.count(token)
            score += 4 * headings.count(token)
            score += body.count(token)
        if score:
            scored.append((score, doc))

    scored.sort(key=lambda i: (-i[0], i[1].slug))
    results = []
    for score, doc in scored[:limit]:
        result = dict(
            slug=doc.slug,
            title=doc.title,
            link=help_doc_link(doc.slug),
            snippet=_snippet(doc.body, tokens),
        )
        results.append({k: v for k, v in result.items() if v is not None})
    return results, len(scored)


def get_help_doc(slug: str) -> Optional[HelpDoc]:
    """Fetch one help doc by its slug.  Returns None when it (or the help directory) is missing."""
    if '..' in slug.split('/'):
        return None
    for doc in load_help_docs():
        if doc.slug == slug:
            return doc
    return None
