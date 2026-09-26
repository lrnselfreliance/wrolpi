"""User bookmarks shown in the navigation bar.

Bookmarks are config-only (no database table).  The config holds a tree: a node with
`children` is a directory, a node with `url` is a bookmark.  Every node has an integer `id`
so the API can address it without relying on names, which need not be unique.

A bookmark `url` may take three forms:
  * a path, `/videos/channel/3`, which the UI renders as an in-app link;
  * a host-relative port, `:8096/web` or `http://:8096/web`, which the UI resolves against
    whatever hostname the browser reached this WROLPi by (LAN IP, mDNS name, hotspot);
  * an absolute URL, `https://example.com`.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from wrolpi.common import ConfigFile, logger
from wrolpi.errors import ValidationError
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod

logger = logger.getChild(__name__)

# The forms a bookmark URL may take.  See the module docstring.
URL_PATTERN = re.compile(r'^(/|:\d+|https?://)', re.IGNORECASE)


@dataclass
class BookmarksConfigValidator:
    version: int = None
    bookmarks: list = field(default_factory=list)


def is_directory(node: dict) -> bool:
    return 'children' in node


def walk(nodes: List[dict], parent: Optional[dict] = None):
    """Yield (node, parent, siblings) for every node in the tree, depth first."""
    for node in nodes:
        yield node, parent, nodes
        if is_directory(node):
            yield from walk(node['children'], node)


def validate_url(url: str) -> str:
    url = (url or '').strip()
    if not url or not URL_PATTERN.match(url):
        raise ValidationError('Bookmark URL must be a path (/videos), a port (:8096/) or an absolute URL (https://)')
    return url


def validate_name(name: str) -> str:
    name = (name or '').strip()
    if not name:
        raise ValidationError('Name is required')
    return name


class BookmarksConfig(ConfigFile):
    file_name = 'bookmarks.yaml'
    default_config = dict(
        version=0,
        bookmarks=[],
    )
    validator = BookmarksConfigValidator

    def import_config(self, file=None, send_events=False):
        super().import_config(file, send_events)
        self.successful_import = True

    @property
    def bookmarks(self) -> List[dict]:
        # A deep copy: the tree is nested, and callers mutate what they get back before
        # assigning it again through the setter.
        from copy import deepcopy
        return deepcopy(list(self._config.get('bookmarks', [])))

    @bookmarks.setter
    def bookmarks(self, value: List[dict]):
        self.update({'bookmarks': value})
        save_bookmarks_config.activate_switch()

    def _next_id(self, bookmarks: List[dict]) -> int:
        ids = [node.get('id', 0) for node, _, _ in walk(bookmarks)]
        return (max(ids) if ids else 0) + 1

    @staticmethod
    def _find(bookmarks: List[dict], node_id: int) -> Tuple[dict, Optional[dict], List[dict]]:
        for node, parent, siblings in walk(bookmarks):
            if node.get('id') == node_id:
                return node, parent, siblings
        raise ValidationError(f'Bookmark {node_id} not found')

    @staticmethod
    def _container(bookmarks: List[dict], parent_id: Optional[int]) -> List[dict]:
        """The list of children that `parent_id` holds; the root list when parent_id is None."""
        if parent_id is None:
            return bookmarks
        parent, _, _ = BookmarksConfig._find(bookmarks, parent_id)
        if not is_directory(parent):
            raise ValidationError(f'Bookmark {parent_id} is not a directory')
        return parent['children']

    @staticmethod
    def _insert(container: List[dict], node: dict, position: Optional[int]):
        if position is None or position >= len(container):
            container.append(node)
        else:
            container.insert(max(position, 0), node)

    def add_bookmark(self, name: str, url: str, new_tab: bool = False, parent_id: int = None,
                     position: int = None) -> dict:
        bookmarks = self.bookmarks
        node = dict(
            id=self._next_id(bookmarks),
            name=validate_name(name),
            url=validate_url(url),
            new_tab=bool(new_tab),
        )
        self._insert(self._container(bookmarks, parent_id), node, position)
        self.bookmarks = bookmarks
        return node

    def add_directory(self, name: str, parent_id: int = None, position: int = None) -> dict:
        bookmarks = self.bookmarks
        node = dict(id=self._next_id(bookmarks), name=validate_name(name), children=[])
        self._insert(self._container(bookmarks, parent_id), node, position)
        self.bookmarks = bookmarks
        return node

    def update_node(self, node_id: int, name: str = None, url: str = None, new_tab: bool = None) -> dict:
        bookmarks = self.bookmarks
        node, _, _ = self._find(bookmarks, node_id)
        if name is not None:
            node['name'] = validate_name(name)
        if is_directory(node):
            if url is not None or new_tab is not None:
                raise ValidationError('A directory has no URL')
        else:
            if url is not None:
                node['url'] = validate_url(url)
            if new_tab is not None:
                node['new_tab'] = bool(new_tab)
        self.bookmarks = bookmarks
        return node

    def delete_node(self, node_id: int) -> dict:
        """Delete a bookmark, or a directory and everything in it."""
        bookmarks = self.bookmarks
        node, _, siblings = self._find(bookmarks, node_id)
        siblings.remove(node)
        self.bookmarks = bookmarks
        return node

    def move_node(self, node_id: int, parent_id: Optional[int], position: Optional[int] = None) -> dict:
        """Move a node into `parent_id` (None = root) at `position` (None = end)."""
        bookmarks = self.bookmarks
        node, _, siblings = self._find(bookmarks, node_id)
        if parent_id == node_id:
            raise ValidationError('Cannot move a directory into itself')
        if is_directory(node) and parent_id is not None:
            descendants = {n['id'] for n, _, _ in walk(node['children'])}
            if parent_id in descendants:
                raise ValidationError('Cannot move a directory into its own child')
        container = self._container(bookmarks, parent_id)
        # Remove after resolving the container so an unknown parent leaves the tree untouched.
        siblings.remove(node)
        self._insert(container, node, position)
        self.bookmarks = bookmarks
        return node


BOOKMARKS_CONFIG: BookmarksConfig = BookmarksConfig()

# Test override.
TEST_BOOKMARKS_CONFIG = None


def get_bookmarks_config() -> BookmarksConfig:
    global TEST_BOOKMARKS_CONFIG
    if isinstance(TEST_BOOKMARKS_CONFIG, ConfigFile):
        return TEST_BOOKMARKS_CONFIG
    return BOOKMARKS_CONFIG


@register_switch_handler('save_bookmarks_config')
def save_bookmarks_config():
    get_bookmarks_config().save()


save_bookmarks_config: ActivateSwitchMethod
