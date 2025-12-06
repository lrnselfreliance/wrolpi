"""
Collection Library Functions

Provides generic operations for collections of any kind (domains, channels, etc.).
These functions are used by both the unified collection API and legacy endpoints.
"""
import asyncio
from typing import List, Optional, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from wrolpi.common import logger, get_relative_to_media_directory
from wrolpi.db import get_db_session, optional_session
from wrolpi.errors import ValidationError
from wrolpi.events import Events
from wrolpi.tags import Tag
from .errors import UnknownCollection
from .models import Collection, validate_collection_directory

logger = logger.getChild(__name__)

__all__ = [
    'get_collections',
    'get_collection_with_stats',
    'update_collection',
    'refresh_collection',
    'tag_collection',
    'get_tag_info',
    'delete_collection',
    'search_collections',
]


@optional_session
def get_collections(kind: Optional[str] = None, session: Session = None) -> List[dict]:
    """
    Get all collections, optionally filtered by kind.

    Args:
        kind: Optional collection kind to filter by (e.g., 'domain', 'channel')
        session: Database session

    Returns:
        List of collection dicts with statistics for each collection type
    """
    query = session.query(Collection)

    if kind:
        query = query.filter(Collection.kind == kind)

    collections = query.order_by(Collection.name).all()

    # Convert to JSON and add type-specific statistics
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

        # Add type-specific statistics
        if collection.kind == 'domain':
            # Add archive statistics for domain collections
            # Local imports to avoid circular import: collections -> archive -> collections
            from modules.archive import Archive
            from wrolpi.files.models import FileGroup

            stats_query = session.query(
                func.count(Archive.id).label('archive_count'),
                func.sum(FileGroup.size).label('size')
            ).outerjoin(
                FileGroup, FileGroup.id == Archive.file_group_id
            ).filter(
                Archive.collection_id == collection.id
            ).one()

            data['archive_count'] = stats_query.archive_count or 0
            data['size'] = stats_query.size or 0
            data['domain'] = data['name']  # Alias for backward compatibility

        elif collection.kind == 'channel':
            # Add video statistics for channel collections
            # Local imports to avoid circular import: collections -> videos -> collections
            from modules.videos.models import Video, Channel
            from wrolpi.files.models import FileGroup

            # Get the Channel associated with this collection
            channel = session.query(Channel).filter(
                Channel.collection_id == collection.id
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
                data['channel_id'] = channel.id  # Include actual Channel ID for frontend links
            else:
                data['video_count'] = 0
                data['total_size'] = 0
                data['channel_id'] = None

        result.append(data)

    return result


@optional_session
def get_collection_with_stats(collection_id: int, session: Session = None) -> dict:
    """
    Get a single collection with type-specific statistics.

    Args:
        collection_id: The collection ID
        session: Database session

    Returns:
        Collection dict with statistics

    Raises:
        UnknownCollection: If collection not found
    """
    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    # Get base collection data
    data = collection.__json__()

    # Add type-specific statistics
    # This can be extended for different collection types
    if collection.kind == 'domain':
        # Add archive statistics for domain collections
        # Local imports to avoid circular import: collections -> archive -> collections
        from modules.archive import Archive
        from wrolpi.files.models import FileGroup

        stats_query = session.query(
            func.count(Archive.id).label('archive_count'),
            func.sum(FileGroup.size).label('size')
        ).outerjoin(
            FileGroup, FileGroup.id == Archive.file_group_id
        ).filter(
            Archive.collection_id == collection_id
        ).one()

        data['archive_count'] = stats_query.archive_count or 0
        data['size'] = stats_query.size or 0
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

    return data


@optional_session
def update_collection(
        collection_id: int,
        directory: Optional[str] = None,
        tag_name: Optional[str] = None,
        description: Optional[str] = None,
        session: Session = None
) -> Collection:
    """
    Update a collection's properties.

    Args:
        collection_id: The collection ID
        directory: New directory (relative or absolute path), or None to clear
        tag_name: New tag name, empty string to clear, or None to leave unchanged
        description: New description, or None to leave unchanged
        session: Database session

    Returns:
        Updated Collection object

    Raises:
        UnknownCollection: If collection not found
        ValidationError: If validation fails
    """
    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    # Update directory if provided
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
            # Set or create tag
            if not collection.directory:
                raise ValidationError(
                    f"Collection '{collection.name}' has no directory. "
                    f"Set a directory before tagging."
                )
            tag = session.query(Tag).filter_by(name=tag_name).one_or_none()
            if not tag:
                tag = Tag(name=tag_name)
                session.add(tag)
                session.flush()
            collection.tag_id = tag.id
        elif tag_name == '':
            # Clear tag (empty string explicitly clears)
            collection.tag_id = None

    session.flush()

    # Trigger domain config save if this is a domain collection
    if collection.kind == 'domain':
        # Local import to avoid circular import: collections -> archive -> collections
        from modules.archive.lib import save_domains_config
        save_domains_config.activate_switch()

    return collection


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
    from wrolpi.files.lib import refresh_files

    with get_db_session() as session:
        collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

        if not collection:
            raise UnknownCollection(f"Collection with ID {collection_id} not found")

        if not collection.directory:
            raise ValidationError(
                f"Collection '{collection.name}' has no directory. "
                f"Set a directory before refreshing."
            )

        directory = collection.directory

    # Refresh files asynchronously
    asyncio.ensure_future(refresh_files([directory], send_events=send_events))

    if send_events:
        relative_dir = get_relative_to_media_directory(directory)
        Events.send_directory_refresh(f'Refreshing: {relative_dir}')


@optional_session(commit=True)
def tag_collection(
        collection_id: int,
        tag_name: Optional[str] = None,
        directory: Optional[str] = None,
        session: Session = None
) -> Dict:
    """
    Tag a collection and optionally move files to a new directory, or remove a tag if no tag_name is provided.

    Args:
        collection_id: The collection ID
        tag_name: Tag name to apply, or None to remove the tag
        directory: Optional new directory for the collection
        session: Database session

    Returns:
        Dict with tag information and suggested directory

    Raises:
        UnknownCollection: If collection not found
        ValidationError: If tagging requirements not met
    """
    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    # If tag_name is None, remove the tag from the collection
    if tag_name is None:
        collection.tag_id = None

        # Update directory if provided (user may want to move files when removing tag)
        old_directory = collection.directory
        if directory:
            target_directory = validate_collection_directory(directory)
            collection.directory = target_directory
        else:
            target_directory = collection.directory

        session.flush()

        # Trigger config save based on collection kind
        if collection.kind == 'domain':
            # Local import to avoid circular import: collections -> archive -> collections
            from modules.archive.lib import save_domains_config
            save_domains_config.activate_switch()
        elif collection.kind == 'channel':
            # Local import to avoid circular import: collections -> videos -> collections
            from modules.videos.lib import save_channels_config
            save_channels_config.activate_switch()

        # Return info about the un-tagging operation
        relative_dir = get_relative_to_media_directory(target_directory) if target_directory else None
        return {
            'collection_id': collection.id,
            'collection_name': collection.name,
            'tag_name': None,
            'directory': str(relative_dir) if relative_dir else None,
            'will_move_files': target_directory is not None and old_directory != target_directory,
        }

    # Get or create the tag
    tag = session.query(Tag).filter_by(name=tag_name).one_or_none()
    if not tag:
        tag = Tag(name=tag_name)
        session.add(tag)
        session.flush()

    # Determine target directory
    if directory:
        # User specified a directory - validate it
        target_directory = validate_collection_directory(directory)
    elif collection.directory:
        # Use existing directory
        target_directory = collection.directory
    else:
        # No directory provided and collection has none - keep it that way
        # Collections can be tagged without a directory for UI search/filtering
        target_directory = None

    # Apply the tag
    collection.tag_id = tag.id
    # Only update directory if we have a target (don't auto-generate for directory-less collections)
    if target_directory is not None:
        collection.directory = target_directory

    session.flush()

    # Trigger config save based on collection kind
    if collection.kind == 'domain':
        # Local import to avoid circular import: collections -> archive -> collections
        from modules.archive.lib import save_domains_config
        save_domains_config.activate_switch()
    elif collection.kind == 'channel':
        # Local import to avoid circular import: collections -> videos -> collections
        from modules.videos.lib import save_channels_config
        save_channels_config.activate_switch()

    # Return info about the tagging operation
    relative_dir = get_relative_to_media_directory(target_directory) if target_directory else None
    return {
        'collection_id': collection.id,
        'collection_name': collection.name,
        'tag_name': tag_name,
        'directory': str(relative_dir) if relative_dir else None,
        'will_move_files': target_directory is not None and collection.directory != target_directory,
    }


@optional_session
def get_tag_info(
        collection_id: int,
        tag_name: Optional[str],
        session: Session = None
) -> Dict:
    """
    Get information about tagging a collection with a specific tag.

    Returns the suggested directory and checks for conflicts with existing collections.
    For collections without a directory, returns suggested_directory=None.

    Args:
        collection_id: The collection ID
        tag_name: Tag name to check
        session: Database session

    Returns:
        Dict with suggested_directory, conflict flag, and optional conflict_message

    Raises:
        UnknownCollection: If collection not found
    """
    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

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


@optional_session
def delete_collection(
        collection_id: int,
        session: Session = None
) -> Dict:
    """
    Delete a collection and orphan its child items.

    For domain collections:
    - Orphans child Archives (sets collection_id to NULL)
    - Deletes the Collection record
    - Triggers domain config save

    Args:
        collection_id: The collection ID to delete
        session: Database session

    Returns:
        Dict with collection information

    Raises:
        UnknownCollection: If collection not found
    """
    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    collection_dict = {
        'id': collection.id,
        'name': collection.name,
        'kind': collection.kind,
    }

    # Orphan child Archives if this is a domain collection
    if collection.kind == 'domain':
        # Local imports to avoid circular import: collections -> archive -> collections
        from modules.archive.models import Archive
        from modules.archive.lib import save_domains_config
        archives = session.query(Archive).filter_by(collection_id=collection_id).all()
        for archive in archives:
            archive.collection_id = None
        session.flush()

        # Trigger domain config save
        save_domains_config.activate_switch()

    # Delete the collection
    session.delete(collection)
    session.flush()

    return collection_dict


@optional_session
def search_collections(
        kind: Optional[str] = None,
        tag_names: Optional[List[str]] = None,
        search_str: Optional[str] = None,
        session: Session = None
) -> List[dict]:
    """
    Search collections by kind, tags, and search string.

    Args:
        kind: Optional collection kind filter
        tag_names: Optional list of tag names to filter by
        search_str: Optional search string for collection names
        session: Database session

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
