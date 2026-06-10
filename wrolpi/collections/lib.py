"""
Collection Library Functions

Provides generic operations for collections of any kind (domains, channels, etc.).
These functions are used by both the unified collection API and legacy endpoints.
"""
import pathlib
from typing import List, Optional, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from wrolpi import flags
from wrolpi.common import logger, get_relative_to_media_directory, TRACE_LEVEL, background_task
from wrolpi.db import get_db_session
from wrolpi.errors import FileWorkerConflict
from wrolpi.errors import ValidationError
from wrolpi.events import Events
from wrolpi.tags import Tag
from .models import Collection, validate_collection_directory
from .types import collection_type_registry

logger = logger.getChild(__name__)

__all__ = [
    'get_collections',
    'get_collection_with_stats',
    'get_domain_statistics',
    'create_collection',
    'add_collection_item',
    'remove_collection_item',
    'reorder_collection_items',
    'update_collection',
    'refresh_collection',
    'tag_collection',
    'get_tag_info',
    'delete_collection',
    'search_collections',
]


def _activate_config_save(kind: str):
    """Activate the config-save switch for the config that owns this kind of Collection.

    Author/subject collections are re-derived on refresh and have no config."""
    if kind == 'domain':
        # Local import to avoid circular import: collections -> archive -> collections
        from modules.archive.lib import save_domains_config
        save_domains_config.activate_switch()
    elif kind == 'channel':
        # Local import to avoid circular import: collections -> videos -> collections
        from modules.videos.lib import save_channels_config
        save_channels_config.activate_switch()
    elif kind == 'playlist':
        from .config import save_playlists_config
        save_playlists_config.activate_switch()


def get_collections(session: Session, kind: Optional[str] = None) -> List[dict]:
    """
    Get all collections, optionally filtered by kind.

    Uses batch queries to fetch statistics for all collections at once,
    avoiding the N+1 query problem that occurs with per-collection queries.

    Args:
        session: Database session
        kind: Optional collection kind to filter by (e.g., 'domain', 'channel')

    Returns:
        List of collection dicts with statistics for each collection type
    """
    # Local imports to avoid circular import: collections -> archive/videos -> collections
    from modules.archive import Archive
    from modules.videos.models import Video, Channel
    from wrolpi.files.models import FileGroup

    query = session.query(Collection)

    if kind:
        query = query.filter(Collection.kind == kind)

    collections = query.order_by(Collection.name).all()

    if not collections:
        return []

    # Separate collections by kind for batch processing
    domain_ids = [c.id for c in collections if c.kind == 'domain']
    channel_ids = [c.id for c in collections if c.kind == 'channel']
    generic_ids = [c.id for c in collections if c.kind not in ('domain', 'channel')]

    # Batch query: Get archive stats for all domain collections at once
    domain_stats_map = {}
    if domain_ids:
        domain_stats = session.query(
            Archive.collection_id,
            func.count(Archive.id).label('archive_count'),
            func.coalesce(func.sum(FileGroup.size), 0).label('size')
        ).outerjoin(
            FileGroup, FileGroup.id == Archive.file_group_id
        ).filter(
            Archive.collection_id.in_(domain_ids)
        ).group_by(Archive.collection_id).all()

        domain_stats_map = {s.collection_id: s for s in domain_stats}

    # Batch query: Get channel info and video stats for all channel collections at once
    channel_stats_map = {}
    if channel_ids:
        channel_stats = session.query(
            Channel.collection_id,
            Channel.id.label('channel_id'),
            func.count(Video.id).label('video_count'),
            func.coalesce(func.sum(FileGroup.size), 0).label('size')
        ).outerjoin(
            Video, Video.channel_id == Channel.id
        ).outerjoin(
            FileGroup, FileGroup.id == Video.file_group_id
        ).filter(
            Channel.collection_id.in_(channel_ids)
        ).group_by(Channel.collection_id, Channel.id).all()

        channel_stats_map = {s.collection_id: s for s in channel_stats}

    # Batch query: Get item counts for generic collections (author, subject, etc.)
    generic_stats_map = {}
    if generic_ids:
        from .models import CollectionItem
        generic_stats = session.query(
            CollectionItem.collection_id,
            func.count(CollectionItem.id).label('item_count'),
        ).filter(
            CollectionItem.collection_id.in_(generic_ids)
        ).group_by(CollectionItem.collection_id).all()

        generic_stats_map = {s.collection_id: s.item_count for s in generic_stats}

    # Convert to JSON and merge batch statistics
    result = []
    for collection in collections:
        data = collection.__json__()

        # Compute minimum download frequency from all downloads
        if collection.downloads:
            # Filter to recurring downloads (frequency > 0) and get minimum
            recurring_frequencies = [d.frequency for d in collection.downloads if d.frequency and d.frequency > 0]
            data['min_download_frequency'] = min(recurring_frequencies) if recurring_frequencies else None
        else:
            data['min_download_frequency'] = None

        # Add type-specific statistics from batch query results
        if collection.kind == 'domain':
            stats = domain_stats_map.get(collection.id)
            data['archive_count'] = stats.archive_count if stats else 0
            data['size'] = int(stats.size) if stats else 0
            data['domain'] = data['name']  # Alias for backward compatibility

        elif collection.kind == 'channel':
            stats = channel_stats_map.get(collection.id)
            if stats:
                data['video_count'] = int(stats.video_count)
                data['total_size'] = int(stats.size)
                data['channel_id'] = stats.channel_id
            else:
                data['video_count'] = 0
                data['total_size'] = 0
                data['channel_id'] = None

        else:
            # Generic collections (author, subject, etc.): use actual CollectionItem count.
            data['item_count'] = generic_stats_map.get(collection.id, 0)

        result.append(data)

    return result


def get_collection_with_stats(session: Session, collection_id: int) -> dict:
    """
    Get a single collection with type-specific statistics.

    Args:
        session: Database session
        collection_id: The collection ID

    Returns:
        Collection dict with statistics

    Raises:
        UnknownCollection: If collection not found
    """
    collection = Collection.find_by_id(session, collection_id)

    # Get base collection data
    data = collection.__json__()

    # Add type-specific statistics
    # This can be extended for different collection types
    if collection.kind == 'domain':
        # Add archive statistics for domain collections
        # Use the detailed statistics function (similar to Channel.get_statistics())
        statistics = get_domain_statistics(session, collection_id)
        data['archive_count'] = statistics['archive_count']
        data['size'] = statistics['size']
        data['statistics'] = statistics
        data['domain'] = data['name']  # Alias for backward compatibility

    elif collection.kind == 'channel':
        # Add video statistics for channel collections
        # Local imports to avoid circular import: collections -> videos -> collections
        from modules.videos.models import Video, Channel
        from wrolpi.files.models import FileGroup

        # Get the Channel associated with this collection
        channel = session.query(Channel).filter(
            Channel.collection_id == collection_id
        ).one_or_none()

        if channel:
            stats_query = session.query(
                func.count(Video.id).label('video_count'),
                func.sum(FileGroup.size).label('size')
            ).outerjoin(
                FileGroup, FileGroup.id == Video.file_group_id
            ).filter(
                Video.channel_id == channel.id
            ).one()

            data['video_count'] = int(stats_query.video_count or 0)
            data['total_size'] = int(stats_query.size or 0)
        else:
            data['video_count'] = 0
            data['total_size'] = 0

    else:
        # Generic collections (author, subject, playlist, etc.): count actual CollectionItem rows.
        from .models import CollectionItem
        item_count = session.query(func.count(CollectionItem.id)).filter(
            CollectionItem.collection_id == collection_id
        ).scalar()
        data['item_count'] = item_count or 0

        # Playlists are manually curated and ordered, so return the full ordered item list.
        if collection.kind == 'playlist':
            data['items'] = [item.dict() for item in collection.items]

    return data


def update_collection(
        session: Session,
        collection_id: int,
        directory: Optional[str] = None,
        tag_name: Optional[str] = None,
        description: Optional[str] = None,
        name: Optional[str] = None,
) -> Collection:
    """
    Update a collection's properties.

    Args:
        session: Database session
        collection_id: The collection ID
        directory: New directory (relative or absolute path), or None to clear
        tag_name: New tag name, empty string to clear, or None to leave unchanged
        description: New description, or None to leave unchanged
        name: New name (rename), or None to leave unchanged

    Returns:
        Updated Collection object

    Raises:
        UnknownCollection: If collection not found
        ValidationError: If validation fails
    """
    collection = Collection.find_by_id(session, collection_id)

    # The managed location before any rename/retag.  The API reports this location for a playlist
    # whose stored directory is None, so the UI round-trips it back; recognize it below and keep
    # storing None (auto-managed) instead of freezing the playlist at the pre-rename path.
    old_default = None
    if collection.kind == 'playlist':
        from .sync import get_playlists_directory, _default_playlist_subdir
        old_default = _default_playlist_subdir(get_playlists_directory(), collection)

    # Rename if provided.
    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError('Collection name cannot be empty')
        if name != collection.name:
            if not collection_type_registry.validate(collection.kind, name):
                raise ValidationError(f'Invalid {collection.kind} name {name!r}')
            duplicate = session.query(Collection).filter(
                Collection.name == name,
                Collection.kind == collection.kind,
                Collection.id != collection.id,
            ).first()
            if duplicate:
                raise ValidationError(f'A {collection.kind} named {name!r} already exists')
            collection.name = name

    # Update directory if provided
    old_directory = collection.directory
    if directory is not None:
        if directory:
            # Convert relative path to absolute with validation
            directory_path = validate_collection_directory(directory)
            collection.directory = directory_path
        else:
            collection.directory = None

    # Update description if provided
    if description is not None:
        collection.description = description

    # Update tag if provided
    if tag_name is not None:
        if tag_name:
            # Set or create tag.  Playlists manage their own on-disk layout (the sync namespaces them
            # under the tag), so they may be tagged without a `directory`; other kinds require one.
            if collection.kind != 'playlist' and not collection.directory:
                raise ValidationError(
                    f"Collection '{collection.name}' has no directory. "
                    f"Set a directory before tagging."
                )
            tag = Tag.get_or_create_tag(session, name=tag_name)
            # Assign the relationship too so `collection.tag_name` is fresh below.
            collection.tag = tag
            collection.tag_id = tag.id
        elif tag_name == '':
            # Clear tag (empty string explicitly clears)
            collection.tag = None
            collection.tag_id = None

    session.flush()

    if collection.kind == 'playlist':
        from .sync import (cleanup_playlist_directory, get_playlists_directory,
                           _default_playlist_subdir, sync_playlists_directory)
        # A directory equal to the managed tag location is not "custom" -- store None so the sync
        # keeps auto-managing it (future tag changes keep moving the playlist automatically).
        # The location is compared both before (`old_default`) and after this update, so a managed
        # playlist stays managed when the UI round-trips the displayed directory with a rename.
        new_default = _default_playlist_subdir(get_playlists_directory(), collection)
        if collection.directory and pathlib.Path(collection.directory) in (new_default, old_default):
            collection.directory = None
            session.flush()
        # Commit before the cleanup and switch activations so the background sync reads the NEW
        # state -- otherwise it can run against the pre-commit row, re-create the old directory,
        # and undo the cleanup (same pattern as tag_collection).
        session.commit()
        # A custom directory lives outside the playlists root, so the sync's orphan pruning never
        # sees it -- clean up the abandoned directory here when the playlist moves away from it.
        if old_directory and str(old_directory) != str(collection.directory or ''):
            cleanup_playlist_directory(old_directory)
        # Re-sync the on-disk playlist (a tag/directory change moves it).
        sync_playlists_directory.activate_switch()

    _activate_config_save(collection.kind)

    return collection


def create_collection(session: Session, name: str, description: Optional[str] = None,
                      kind: str = 'playlist', tag_name: Optional[str] = None) -> Collection:
    """Create a new Collection (defaults to a 'playlist'), optionally with an initial tag.

    Raises:
        ValidationError: if the name is empty/invalid for the kind, or a duplicate exists.
    """
    name = (name or '').strip()
    if not name:
        raise ValidationError('Collection name is required')
    if not collection_type_registry.is_registered(kind):
        raise ValidationError(f'Unknown collection kind: {kind!r}')
    if not collection_type_registry.validate(kind, name):
        description_msg = collection_type_registry.get_description(kind) or 'Invalid name format'
        raise ValidationError(f'Invalid {kind} name {name!r}. {description_msg}')
    # Same rule as update_collection: only playlists can be tagged without a directory, and a new
    # collection never has one yet.
    if tag_name and kind != 'playlist':
        raise ValidationError(f'A new {kind} cannot be created with a tag.  Set a directory first.')

    existing = session.query(Collection).filter_by(name=name, kind=kind).first()
    if existing:
        raise ValidationError(f'A {kind} named {name!r} already exists')

    collection = Collection(name=name, description=description, kind=kind)
    if tag_name:
        tag = Tag.get_or_create_tag(session, name=tag_name)
        # Assign the relationship too so `collection.tag_name` is fresh for serialization.
        collection.tag = tag
        collection.tag_id = tag.id
    session.add(collection)
    session.flush([collection])

    _activate_config_save(kind)
    return collection


def add_collection_item(session: Session, collection_id: int, item_kind: str,
                        file_group_id: Optional[int] = None, zim_id: Optional[int] = None,
                        zim_entry: Optional[str] = None, url: Optional[str] = None,
                        title: Optional[str] = None, position: Optional[int] = None):
    """Add a file/zim/url item to a collection.

    Adding an item that already exists is idempotent: the existing CollectionItem is returned.

    Returns:
        (CollectionItem, created): ``created`` is False when the item already existed.

    Raises:
        UnknownCollection: if the collection does not exist.
        ValidationError: if the item is invalid for its type.
    """
    from .models import CollectionItem
    collection = Collection.find_by_id(session, collection_id)

    if item_kind == 'file':
        from wrolpi.files.models import FileGroup
        if not file_group_id:
            raise ValidationError('file_group_id is required for a file item')
        file_group = session.query(FileGroup).filter_by(id=file_group_id).one_or_none()
        if not file_group:
            raise ValidationError(f'No FileGroup with id {file_group_id}')
        created = session.query(CollectionItem).filter_by(
            collection_id=collection_id, file_group_id=file_group_id).first() is None
        try:
            item = collection.add_file_group(file_group, position=position, session=session)
        except ValueError as e:
            raise ValidationError(str(e))
        if title:
            item.title = title
    elif item_kind == 'zim':
        created = session.query(CollectionItem).filter_by(
            collection_id=collection_id, zim_id=zim_id, zim_entry=zim_entry).first() is None
        try:
            item = collection.add_zim_entry(session, zim_id, zim_entry, title=title, position=position)
        except ValueError as e:
            raise ValidationError(str(e))
    elif item_kind == 'url':
        created = session.query(CollectionItem).filter_by(
            collection_id=collection_id, url=url).first() is None
        try:
            item = collection.add_url(session, url, title=title, position=position)
        except ValueError as e:
            raise ValidationError(str(e))
    else:
        raise ValidationError(f'Unknown item_kind: {item_kind!r}')

    session.flush()
    from .config import save_playlists_config
    save_playlists_config.activate_switch()
    from .sync import sync_playlists_directory
    sync_playlists_directory.activate_switch()
    return item, created


def remove_collection_item(session: Session, collection_id: int, item_id: int) -> bool:
    """Remove an item from a collection by CollectionItem id.  Returns True if removed."""
    collection = Collection.find_by_id(session, collection_id)
    removed = collection.remove_item(session, item_id)
    if removed:
        from .config import save_playlists_config
        save_playlists_config.activate_switch()
        from .sync import sync_playlists_directory
        sync_playlists_directory.activate_switch()
    return removed


def reorder_collection_items(session: Session, collection_id: int, item_ids: List[int]):
    """Reorder a collection's items from a full list of CollectionItem ids."""
    collection = Collection.find_by_id(session, collection_id)
    collection.reorder_items(session, item_ids)
    from .config import save_playlists_config
    save_playlists_config.activate_switch()
    from .sync import sync_playlists_directory
    sync_playlists_directory.activate_switch()


def _get_external_collection_file_paths(session, collection_id: int, directory: pathlib.Path) -> list[pathlib.Path]:
    """Return primary_path for FileGroups associated with a collection but outside its directory.

    Checks both CollectionItem relationships and kind-specific relationships (e.g. Channel → Video)."""
    from wrolpi.files.models import FileGroup
    from .models import CollectionItem
    dir_str = f'{directory}/'

    external_paths = []

    # Check CollectionItems.
    item_fgs = session.query(FileGroup).join(
        CollectionItem, CollectionItem.file_group_id == FileGroup.id
    ).filter(
        CollectionItem.collection_id == collection_id,
        FileGroup.directory != str(directory),
        ~FileGroup.directory.startswith(dir_str),
    ).all()
    for fg in item_fgs:
        external_paths.append(fg.primary_path)

    # For channel-kind collections, also check Videos linked via Channel.
    collection = session.query(Collection).filter_by(id=collection_id).one()
    if collection.kind == 'channel':
        from modules.videos.models import Channel
        channel = session.query(Channel).filter_by(collection_id=collection_id).one_or_none()
        if channel:
            channel_paths = Channel._get_external_file_paths(session, channel.id, directory)
            # Deduplicate against paths already found via CollectionItems.
            seen = set(external_paths)
            for p in channel_paths:
                if p not in seen:
                    external_paths.append(p)

    return external_paths


def refresh_collection(collection_id: int, send_events: bool = True) -> None:
    """
    Refresh all files in a collection's directory.

    Args:
        collection_id: The collection ID
        send_events: Whether to send events about the refresh

    Raises:
        UnknownCollection: If collection not found
        ValidationError: If collection has no directory
    """
    # Local import to avoid circular import: collections -> files -> collections
    from wrolpi.files.worker import file_worker

    with get_db_session() as session:
        collection = Collection.find_by_id(session, collection_id)

        if not collection.directory:
            raise ValidationError(
                f"Collection '{collection.name}' has no directory. "
                f"Set a directory before refreshing."
            )

        directory = collection.directory
        # Find files associated with this collection but outside its directory.
        external_paths = _get_external_collection_file_paths(session, collection_id, directory)

    # Refresh files asynchronously
    file_worker.queue_refresh([directory] + external_paths)

    if send_events:
        relative_dir = get_relative_to_media_directory(directory)
        Events.send_directory_refresh(f'Refreshing: {relative_dir}')


async def _background_move_collection(collection_id: int, target_directory: pathlib.Path):
    """Helper to run collection move in background with its own database session.

    This allows the move to continue even if the original HTTP request is cancelled
    (e.g., user closes browser tab).
    """
    try:
        with get_db_session(commit=True) as session:
            collection = session.query(Collection).filter_by(id=collection_id).one_or_none()
            if not collection:
                logger.error(f'_background_move_collection: collection {collection_id} not found')
                Events.send_file_move_failed(f'Collection move failed: collection not found')
                return
            await collection.move_collection(target_directory, session, send_events=True)
    except Exception as e:
        logger.error(f'_background_move_collection: failed for collection_id={collection_id}', exc_info=e)
        Events.send_file_move_failed(f'Collection move failed: {e}')


async def tag_collection(
        session: Session,
        collection_id: int,
        tag_name: Optional[str] = None,
        directory: Optional[str] = None,
) -> Dict:
    """
    Tag a collection and optionally move files to a new directory, or remove a tag if no tag_name is provided.

    Args:
        session: Database session
        collection_id: The collection ID
        tag_name: Tag name to apply, or None to remove the tag
        directory: Optional new directory for the collection

    Returns:
        Dict with tag information and suggested directory

    Raises:
        UnknownCollection: If collection not found
        ValidationError: If tagging requirements not met
        FileWorkerConflict: If a file operation is in progress and directory change is requested
    """
    collection = Collection.find_by_id(session, collection_id)

    # Track old directory before any changes for potential file moving
    old_directory = collection.directory

    # Determine target directory.  Collections can be tagged without a directory for UI
    # search/filtering, so a missing directory is left missing.
    if directory:
        target_directory = validate_collection_directory(directory)
    else:
        target_directory = collection.directory

    # Check if we need to move files
    need_to_move = (
            target_directory is not None and
            old_directory is not None and
            target_directory != old_directory
    )

    if __debug__ and logger.isEnabledFor(TRACE_LEVEL):
        logger.trace(f'tag_collection: {repr(collection.name)} need_to_move={need_to_move}, '
                     f'{old_directory} -> {target_directory}')

    if need_to_move and flags.file_worker_busy.is_set():
        raise FileWorkerConflict('Refusing to move collection while FileWorker is busy')

    # Apply (or remove) the tag
    if tag_name is None:
        collection.tag_id = None
    else:
        collection.tag_id = Tag.get_or_create_tag(session, name=tag_name).id
        # Only update directory if we have a target (don't auto-generate for directory-less
        # collections).  Directory update is handled by move_collection if need_to_move.
        if target_directory is not None and not need_to_move:
            collection.directory = target_directory

    session.flush()

    _activate_config_save(collection.kind)

    # Move files if directory changed - run in background so closing tab won't cancel it
    if need_to_move:
        target_directory.mkdir(parents=True, exist_ok=True)
        # Commit tag changes before starting background move
        session.commit()
        background_task(_background_move_collection(collection.id, target_directory))

    relative_dir = get_relative_to_media_directory(target_directory) if target_directory else None
    return {
        'collection_id': collection.id,
        'collection_name': collection.name,
        'tag_name': tag_name,
        'directory': str(relative_dir) if relative_dir else None,
        'will_move_files': need_to_move,
    }


def get_tag_info(
        session: Session,
        collection_id: int,
        tag_name: Optional[str],
) -> Dict:
    """
    Get information about tagging a collection with a specific tag.

    Returns the suggested directory and checks for conflicts with existing collections.
    For collections without a directory, returns suggested_directory=None.

    Args:
        session: Database session
        collection_id: The collection ID
        tag_name: Tag name to check

    Returns:
        Dict with suggested_directory, conflict flag, and optional conflict_message

    Raises:
        UnknownCollection: If collection not found
    """
    collection = Collection.find_by_id(session, collection_id)

    # Playlists: suggest the managed tag location (<playlists>/<tag>/<name>), even when the
    # playlist has no explicit directory (most don't -- the sync manages their location).
    if collection.kind == 'playlist':
        from wrolpi.common import escape_file_name
        from .sync import get_playlists_directory
        base = get_playlists_directory()
        if tag_name:
            base = base / escape_file_name(tag_name)
        suggested = base / escape_file_name(collection.name)
        return {
            'suggested_directory': str(get_relative_to_media_directory(suggested)),
            'conflict': False,
            'conflict_message': None,
        }

    # For collections without a directory, return None - no directory suggestions needed
    if collection.directory is None:
        return {
            'suggested_directory': None,
            'conflict': False,
            'conflict_message': None,
        }

    # Use the collection's format_directory method to get the suggested directory
    suggested_directory = collection.format_directory(tag_name)

    # Check for directory conflicts with other domain collections
    conflict = False
    conflict_message = None

    # Only check for conflicts if this is a domain collection
    if collection.kind == 'domain':
        # Check if another domain collection already has this directory
        existing_domain = session.query(Collection).filter(
            Collection.directory == str(suggested_directory),
            Collection.kind == 'domain',
            Collection.id != collection_id
        ).first()

        if existing_domain:
            conflict = True
            conflict_message = (
                f"A domain collection '{existing_domain.name}' already uses this directory. "
                f"Choose a different tag or directory."
            )

    # Return relative path for the frontend
    relative_dir = get_relative_to_media_directory(suggested_directory)

    return {
        'suggested_directory': str(relative_dir),
        'conflict': conflict,
        'conflict_message': conflict_message,
    }


def delete_collection(
        session: Session,
        collection_id: int,
) -> Dict:
    """
    Delete a collection and orphan its child items.

    For domain collections:
    - Orphans child Archives (sets collection_id to NULL)
    - Deletes the Collection record
    - Triggers domain config save

    For channel collections:
    - Orphans child Videos (sets channel_id to NULL)
    - Deletes the Channel record
    - Deletes the Collection record
    - Triggers channel config save

    Args:
        session: Database session
        collection_id: The collection ID to delete

    Returns:
        Dict with collection information

    Raises:
        UnknownCollection: If collection not found
    """
    collection = Collection.find_by_id(session, collection_id)

    collection_dict = {
        'id': collection.id,
        'name': collection.name,
        'kind': collection.kind,
    }

    # Orphan child Archives if this is a domain collection
    if collection.kind == 'domain':
        # Local import to avoid circular import: collections -> archive -> collections
        from modules.archive.models import Archive
        archives = session.query(Archive).filter_by(collection_id=collection_id).all()
        for archive in archives:
            archive.collection_id = None
        session.flush()

    # Orphan child Videos and delete Channel if this is a channel collection
    elif collection.kind == 'channel':
        # Local imports to avoid circular import: collections -> videos -> collections
        from modules.videos.models import Channel, Video

        # Find the Channel that references this Collection
        channel = session.query(Channel).filter_by(collection_id=collection_id).one_or_none()
        if channel:
            # Orphan all Videos (set channel_id = None)
            videos = session.query(Video).filter_by(channel_id=channel.id).all()
            for video in videos:
                video.channel_id = None
            session.flush()

            # Delete the Channel (before Collection to satisfy FK)
            session.delete(channel)
            session.flush()

    # A playlist's custom directory lives outside the playlists root; remember it so its managed
    # files can be cleaned up after the delete (the sync's orphan pruning only covers the root).
    playlist_custom_directory = collection.directory if collection.kind == 'playlist' else None

    # Delete the collection
    session.delete(collection)
    session.flush()

    # Clean up the playlist's on-disk directory and re-sync.
    if collection_dict['kind'] == 'playlist':
        from .sync import cleanup_playlist_directory, sync_playlists_directory
        # Commit before the cleanup and switch activations so the background sync reads the NEW
        # state (the deleted row); a sync of pre-commit state would re-create the directory.
        session.commit()
        if playlist_custom_directory:
            cleanup_playlist_directory(playlist_custom_directory)
        sync_playlists_directory.activate_switch()

    # Persist the deletion to the owning config.
    _activate_config_save(collection_dict['kind'])

    return collection_dict


def search_collections(
        session: Session,
        kind: Optional[str] = None,
        tag_names: Optional[List[str]] = None,
        search_str: Optional[str] = None,
) -> List[dict]:
    """
    Search collections by kind, tags, and search string.

    Args:
        session: Database session
        kind: Optional collection kind filter
        tag_names: Optional list of tag names to filter by
        search_str: Optional search string for collection names

    Returns:
        List of matching collection dicts
    """
    query = session.query(Collection)

    # Filter by kind
    if kind:
        query = query.filter(Collection.kind == kind)

    # Filter by tags
    if tag_names:
        query = query.join(Tag).filter(Tag.name.in_(tag_names))

    # Filter by search string
    if search_str:
        query = query.filter(Collection.name.ilike(f'%{search_str}%'))

    # Order by name
    query = query.order_by(Collection.name)

    collections = query.all()
    return [collection.__json__() for collection in collections]


def get_domain_statistics(session: Session, collection_id: int) -> Dict:
    """
    Get detailed statistics for a domain collection.

    Similar to Channel.get_statistics(), this returns comprehensive stats about
    a domain collection's archives.

    Args:
        session: Database session
        collection_id: The domain collection ID

    Returns:
        Dict with:
        - archive_count: Number of archives in the domain
        - size: Total size of all archive files
        - largest_archive: Size of the largest archive
        - archive_tags: Count of archives that have at least one tag
    """
    # Local imports to avoid circular import: collections -> archive -> collections
    from modules.archive.models import Archive
    from wrolpi.files.models import FileGroup
    from wrolpi.tags import TagFile

    # Use a single query with aggregate functions similar to Channel.get_statistics()
    stats_query = session.query(
        func.count(Archive.id).label('archive_count'),
        func.coalesce(func.sum(FileGroup.size), 0).label('size'),
        func.coalesce(func.max(FileGroup.size), 0).label('largest_archive'),
        func.count(Archive.id).filter(TagFile.file_group_id.isnot(None)).label('archive_tags')
    ).outerjoin(
        FileGroup, FileGroup.id == Archive.file_group_id
    ).outerjoin(
        TagFile, FileGroup.id == TagFile.file_group_id
    ).filter(
        Archive.collection_id == collection_id
    ).one()

    return {
        'archive_count': stats_query.archive_count or 0,
        'size': int(stats_query.size or 0),
        'largest_archive': int(stats_query.largest_archive or 0),
        'archive_tags': stats_query.archive_tags or 0,
    }
