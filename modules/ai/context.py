"""The library map: a compact, live overview of this WROLPi injected into every chat.

Small models answer from what is in context.  Without this block the model must spend a tool
round-trip (minutes on slow hardware) just to learn what channels exist — and it still misread
spellings.  With it, exact names, counts, and today's date are in front of the model before the
first token.  Kept to a few hundred tokens: names are capped and the block is cached briefly."""
import time
from typing import List, Optional

from sqlalchemy import func

from wrolpi.common import logger
from wrolpi.dates import now
from wrolpi.db import get_db_session

logger = logger.getChild(__name__)

# At most this many names per category; a huge library lists the rest as a count.
MAX_NAMES = 30
CACHE_SECONDS = 60

_cache = dict(text=None, expires=0.0)


def _capped_names(names: List[str], label: str) -> str:
    names = [i for i in names if i]
    if not names:
        return f'{label}: none'
    listed = ', '.join(sorted(names)[:MAX_NAMES])
    extra = f' (and {len(names) - MAX_NAMES} more)' if len(names) > MAX_NAMES else ''
    return f'{label} ({len(names)}): {listed}{extra}'


def build_library_context() -> str:
    """Build the library overview.  Every query here must stay cheap (counts and name lists)."""
    from modules.archive.models import Archive
    from modules.docs.models import Doc
    from modules.videos.models import Video
    from modules.zim.models import Zim
    from wrolpi.collections.models import Collection

    lines = [f'Today is {now().strftime("%A, %B %d, %Y")}.', "The user's library contains:"]
    with get_db_session() as session:
        counts = {model.__name__: session.query(func.count(model.id)).scalar() or 0
                  for model in (Video, Archive, Doc)}
        lines.append(f'- {counts["Video"]} videos, {counts["Archive"]} archived web pages,'
                     f' {counts["Doc"]} documents/ebooks.')

        collections = session.query(Collection.kind, Collection.name).all()
        channels = [name for kind, name in collections if kind == 'channel']
        domains = [name for kind, name in collections if kind == 'domain']
        lines.append(f'- {_capped_names(channels, "Video channels")}')
        lines.append(f'- {_capped_names(domains, "Archived websites")}')

        zims = session.query(Zim).all()
        zim_titles = []
        for zim in zims:
            try:
                zim_titles.append(zim.zim_metadata.title)
            except Exception:
                zim_titles.append(zim.path.name if zim.path else None)
        lines.append(f'- {_capped_names(zim_titles, "Zim encyclopedias")}')

    try:
        from modules.inventory.common import get_inventory_configs
        inventories = [i.get('name') for i in get_inventory_configs().all_inventories()]
        lines.append(f'- {_capped_names(inventories, "Inventories")}')
    except Exception as e:
        logger.debug('Library context could not list inventories', exc_info=e)

    lines.append('Use the exact names above; user spellings may differ.')
    return '\n'.join(lines)


def get_library_context() -> Optional[str]:
    """The cached library overview; None when it cannot be built (chat proceeds without it)."""
    if _cache['text'] is not None and time.time() < _cache['expires']:
        return _cache['text']
    try:
        text = build_library_context()
    except Exception as e:
        logger.warning('Could not build the library context', exc_info=e)
        return _cache['text']
    _cache.update(text=text, expires=time.time() + CACHE_SECONDS)
    return text
