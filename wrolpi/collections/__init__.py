from . import lib
from . import sync  # noqa: F401  (registers the sync_playlists_directory switch handler)
from .config import (playlists_config, PlaylistsConfig, save_playlists_config)
from .errors import UnknownCollection
from .models import Collection, CollectionItem
from .types import collection_type_registry

__all__ = [
    'Collection',
    'CollectionItem',
    'PlaylistsConfig',
    'UnknownCollection',
    'collection_type_registry',
    'lib',
    'playlists_config',
    'save_playlists_config',
]
