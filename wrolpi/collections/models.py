import pathlib
from typing import Optional, List

from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Index, UniqueConstraint, func, BigInteger, or_
from sqlalchemy.orm import relationship, Session
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi import flags
from wrolpi.common import Base, ModelHelper, logger, get_media_directory, get_relative_to_media_directory, \
    unique_by_predicate, TRACE_LEVEL
from wrolpi.downloader import Download, save_downloads_config
from wrolpi.errors import ValidationError
from wrolpi.events import Events
from wrolpi.files.lib import move as move_files, refresh_files
from wrolpi.files.models import FileGroup
from wrolpi.media_path import MediaPathType
from wrolpi.tags import Tag
from wrolpi.tags import save_tags_config
from .errors import UnknownCollection
from .types import collection_type_registry

logger = logger.getChild(__name__)

__all__ = ['Collection', 'CollectionItem']


def validate_collection_directory(directory: pathlib.Path) -> pathlib.Path:
    """Validate and normalize a collection directory path.

    Args:
        directory: Directory path (relative or absolute)

    Returns:
        Normalized absolute path under media directory

    Raises:
        ValidationError: If absolute path is outside media directory
    """
    media_directory = get_media_directory()
    directory = pathlib.Path(directory)

    if not directory.is_absolute():
        # Relative path - make absolute under media directory
        directory = media_directory / directory
    else:
        # Absolute path - must be under media directory
        try:
            directory.relative_to(media_directory)
        except ValueError:
            raise ValidationError(
                f"Collection directory must be under media directory {media_directory}, "
                f"but got {directory}"
            )

    return directory


class Collection(ModelHelper, Base):
    """
    A Collection is a grouping of FileGroups (videos, archives, ebooks, etc).

    Collections can be:
    - Directory-restricted: Only contains files within a specific directory tree
    - Unrestricted: Contains files from anywhere in the media library

    Collections maintain order through the CollectionItem junction table.
    """
    __tablename__ = 'collection'

    __table_args__ = (
        UniqueConstraint('directory', name='uq_collection_directory'),
        UniqueConstraint('name', 'kind', name='uq_collection_name_kind'),
        Index('idx_collection_kind', 'kind'),
        Index('idx_collection_item_count', 'item_count'),
        Index('idx_collection_total_size', 'total_size'),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)

    # Type of collection to keep separation of kinds (e.g., videos, archives, books, etc.)
    kind = Column(String, nullable=False, server_default='channel', default='channel')

    # Optional directory restriction - if set, only files in this directory tree can be added
    directory: Optional[pathlib.Path] = Column(MediaPathType, nullable=True)

    # Optional tag relationship (similar to Channel)
    tag_id = Column(Integer, ForeignKey('tag.id'))
    tag = relationship('Tag', primaryjoin='Collection.tag_id==Tag.id')

    created_date = Column(DateTime, server_default=func.now(), nullable=False)

    # Columns updated by triggers (similar to Channel)
    item_count = Column(Integer, default=0, nullable=False)
    total_size = Column(BigInteger, default=0, nullable=False)

    # Relationship to items (ordered)
    items: InstrumentedList = relationship(
        'CollectionItem',
        primaryjoin='Collection.id==CollectionItem.collection_id',
        back_populates='collection',
        order_by='CollectionItem.position',
        cascade='all, delete-orphan'
    )

    # Relationship to downloads
    downloads: InstrumentedList = relationship(
        'Download',
        primaryjoin='Download.collection_id==Collection.id',
        back_populates='collection'
    )

    def __repr__(self):
        return f'<Collection id={self.id} name={repr(self.name)} directory={self.directory} items={self.item_count}>'

    @property
    def tag_name(self) -> str | None:
        return self.tag.name if self.tag else None

    @property
    def location(self) -> str:
        """The href of the collection in the App."""
        return f'/collections/{self.id}'

    @property
    def is_directory_restricted(self) -> bool:
        """Returns True if this collection is restricted to a specific directory."""
        return self.directory is not None

    @staticmethod
    def is_valid_domain_name(name: str) -> bool:
        """
        Validate that a name is a valid domain format.

        A valid domain must:
        - Be a string
        - Contain at least one "." (e.g., "example.com")
        - Not start or end with "."

        Examples:
            Valid: "example.com", "sub.example.com", "a.b.c"
            Invalid: "example", "example.", ".example", "."

        Args:
            name: The domain name to validate

        Returns:
            True if valid domain format, False otherwise
        """
        # Use the registry for validation
        return collection_type_registry.validate('domain', name)

    def to_config(self) -> dict:
        """
        Export this Collection's metadata to a config dict.
        Only includes the minimum data necessary for reconstruction.
        """
        config = {
            'name': self.name,
            'kind': self.kind,
        }

        if self.description:
            config['description'] = self.description

        if self.directory:
            # Store absolute path for consistency with Channel config
            config['directory'] = str(self.directory)

        config['tag_name'] = self.tag_name

        # Include downloads if any exist
        if self.downloads:
            config['downloads'] = [
                {'url': d.url, 'frequency': d.frequency}
                for d in self.downloads
            ]

        return config

    def get_or_create_download(self, session: Session, url: str, frequency: int,
                               reset_attempts: bool = False,
                               downloader_name: str = None,
                               sub_downloader_name: str = None) -> 'Download':
        """Get or create a Download for this Collection.

        Args:
            session: Database session
            url: The URL to download
            frequency: Seconds between re-downloading
            reset_attempts: Reset download attempts if True
            downloader_name: Name of the downloader to use
            sub_downloader_name: Name of the sub-downloader for child downloads

        Returns:
            The Download instance

        Raises:
            InvalidDownload: If url or frequency is missing
        """
        # Local imports to avoid circular import: collections -> downloader -> collections
        from wrolpi.downloader import Download, download_manager
        from wrolpi.errors import InvalidDownload

        if not url:
            raise InvalidDownload('Cannot get Download without url')
        if not frequency:
            raise InvalidDownload('Download for Collection must have a frequency')

        download = Download.get_by_url(session, url)
        if not download:
            download = download_manager.recurring_download(
                session, url, frequency, downloader_name,
                sub_downloader_name=sub_downloader_name,
                destination=str(self.directory) if self.directory else None,
                reset_attempts=reset_attempts,
            )
        if reset_attempts:
            download.attempts = 0
        download.collection_id = self.id
        return download

    @staticmethod
    def from_config(session: Session, data: dict) -> 'Collection':
        """
        Create or update a Collection from config data.

        If the collection has a directory, auto-populate with FileGroups from that directory.
        If the collection has no directory, items are managed manually (not from config).

        Args:
            session: Database session
            data: Config dict containing collection metadata

        Returns:
            The created or updated Collection

        Raises:
            ValueError: If required fields are missing
        """
        name = data.get('name')
        if not name:
            raise ValueError('Collection config must have a name')

        description = data.get('description')
        directory = data.get('directory')
        tag_name = data.get('tag_name')
        kind = (data.get('kind') or 'channel').strip()
        # Validate known kinds (forward-compatible: allow future values)
        if kind not in {'channel', 'domain'}:
            logger.warning(f"Unknown collection kind '{kind}', defaulting to 'channel'")
            kind = 'channel'

        # Validate collection name using the type registry
        if not collection_type_registry.validate(kind, name):
            description = collection_type_registry.get_description(kind) or "Invalid name format"
            raise ValueError(f'Invalid {kind} name for collection: {repr(name)}. {description}')

        # Convert directory to absolute path if provided, with validation
        if directory:
            directory = validate_collection_directory(directory)

        # Try to find existing collection:
        # - If directory is provided, resolve by unique directory
        # - Otherwise, fall back to first match by (name, kind)
        if directory:
            collection = Collection.get_by_path(session, directory)
        else:
            collection = session.query(Collection).filter_by(name=name, kind=kind).first()

        if collection:
            # Update existing collection
            logger.debug(f'Updating collection from config: {name}')
            collection.description = description
            collection.directory = directory
            collection.kind = kind

            if tag_name:
                tag = Tag.get_by_name(session, tag_name)
                if tag:
                    collection.tag = tag
                else:
                    logger.warning(f'Tag {repr(tag_name)} not found for collection {repr(name)}')
                    collection.tag = None
            else:
                collection.tag = None
        else:
            # Create new collection
            logger.info(f'Creating new collection from config: {name}')
            collection = Collection(
                name=name,
                description=description,
                directory=directory,
                kind=kind,
            )

            if tag_name:
                tag = Tag.get_by_name(session, tag_name)
                if tag:
                    collection.tag = tag
                else:
                    logger.warning(f'Tag {repr(tag_name)} not found for collection {repr(name)}')

            session.add(collection)

        session.flush([collection])

        # If directory-restricted, populate with FileGroups from that directory
        if collection.directory and collection.directory.is_dir():
            logger.info(f'Populating collection {repr(name)} from directory {collection.directory}')
            collection.populate_from_directory(session)
        elif collection.directory and not collection.directory.is_dir():
            logger.warning(f'Collection directory does not exist: {collection.directory}')

        return collection

    @staticmethod
    def batch_from_config(session: Session, data_list: List[dict]) -> List['Collection']:
        """
        Create or update multiple Collections from config data in batch.
        More efficient than calling from_config() in a loop because it pre-fetches
        existing collections and tags in bulk queries.

        NOTE: This method does NOT call populate_from_directory(). For channel collections,
        use claim_videos_for_channels() after batch_from_config() to assign videos to channels.

        Args:
            session: Database session
            data_list: List of config dicts containing collection metadata

        Returns:
            List of created or updated Collections
        """
        if not data_list:
            return []

        # Step 1: Validate and prepare directories
        directories = []
        for data in data_list:
            directory = data.get('directory')
            if directory:
                directories.append(str(validate_collection_directory(directory)))

        # Step 2: Pre-fetch existing collections by directory in ONE query
        existing_by_directory = {}
        if directories:
            existing = session.query(Collection).filter(
                Collection.directory.in_(directories)
            ).all()
            existing_by_directory = {str(c.directory): c for c in existing}

        # Step 3: Pre-fetch existing collections by (name, kind) for ALL collections
        # This handles cases where directory changed or directory-less collections
        name_kind_pairs = [(d['name'], d.get('kind', 'channel')) for d in data_list]
        existing_by_name_kind = {}
        if name_kind_pairs:
            from sqlalchemy import and_, or_
            conditions = [
                and_(Collection.name == name, Collection.kind == kind)
                for name, kind in name_kind_pairs
            ]
            existing = session.query(Collection).filter(or_(*conditions)).all()
            existing_by_name_kind = {(c.name, c.kind): c for c in existing}

        # Step 4: Pre-fetch all tags in ONE query
        tag_names = {d['tag_name'] for d in data_list if d.get('tag_name')}
        tags_by_name = {}
        if tag_names:
            tags = session.query(Tag).filter(Tag.name.in_(tag_names)).all()
            tags_by_name = {t.name: t for t in tags}

        # Step 5: Process collections
        collections = []
        new_collections = []

        for data in data_list:
            name = data.get('name')
            if not name:
                raise ValueError('Collection config must have a name')

            description = data.get('description')
            directory = data.get('directory')
            tag_name = data.get('tag_name')
            kind = (data.get('kind') or 'channel').strip()

            # Validate known kinds
            if kind not in {'channel', 'domain'}:
                logger.warning(f"Unknown collection kind '{kind}', defaulting to 'channel'")
                kind = 'channel'

            # Validate collection name using the type registry
            if not collection_type_registry.validate(kind, name):
                description_msg = collection_type_registry.get_description(kind) or "Invalid name format"
                raise ValueError(f'Invalid {kind} name for collection: {repr(name)}. {description_msg}')

            # Convert directory to absolute path if provided
            if directory:
                directory = validate_collection_directory(directory)
                directory_str = str(directory)
            else:
                directory_str = None

            # Find existing collection from pre-fetched data
            # Priority: 1) by directory (if provided), 2) by (name, kind) as fallback
            collection = None
            if directory_str:
                collection = existing_by_directory.get(directory_str)
            # Always check by (name, kind) as fallback - handles directory changes
            if not collection:
                collection = existing_by_name_kind.get((name, kind))

            if collection:
                # Update existing collection
                logger.debug(f'Updating collection from config: {name}')
                collection.description = description
                collection.directory = directory
                collection.kind = kind

                if tag_name:
                    tag = tags_by_name.get(tag_name)
                    if tag:
                        collection.tag = tag
                    else:
                        logger.warning(f'Tag {repr(tag_name)} not found for collection {repr(name)}')
                        collection.tag = None
                else:
                    collection.tag = None
            else:
                # Create new collection
                logger.info(f'Creating new collection from config: {name}')
                collection = Collection(
                    name=name,
                    description=description,
                    directory=directory,
                    kind=kind,
                )

                if tag_name:
                    tag = tags_by_name.get(tag_name)
                    if tag:
                        collection.tag = tag
                    else:
                        logger.warning(f'Tag {repr(tag_name)} not found for collection {repr(name)}')

                new_collections.append(collection)

            collections.append(collection)

        # Step 6: Batch add new collections
        if new_collections:
            session.add_all(new_collections)

        # Single flush for all collections
        session.flush()

        return collections

    def populate_from_directory(self, session: Session):
        """
        Populate this collection with all FileGroups in the collection's directory.
        Only works for directory-restricted collections.
        """

        if not self.is_directory_restricted:
            logger.warning(f'Cannot populate unrestricted collection from directory: {self}')
            return

        if not self.directory.is_dir():
            logger.warning(f'Cannot populate collection, directory does not exist: {self.directory}')
            return

        # Find all FileGroups in this directory tree
        # Use indexed directory column for efficient lookup
        directory_str = str(self.directory)
        file_groups = session.query(FileGroup).filter(
            or_(
                FileGroup.directory == directory_str,
                FileGroup.directory.like(f'{directory_str}/%')
            )
        ).all()

        if not file_groups:
            logger.debug(f'No FileGroups found in {self.directory}')
            return

        # Get existing items to avoid duplicates
        existing_fg_ids = {item.file_group_id for item in self.items}

        # Add new FileGroups
        new_file_groups = [fg for fg in file_groups if fg.id not in existing_fg_ids]
        if new_file_groups:
            self.add_file_groups(session, new_file_groups)
            logger.info(f'Added {len(new_file_groups)} FileGroups to collection {repr(self.name)}')

    def validate_file_group(self, file_group: FileGroup) -> bool:
        """
        Check if a FileGroup can be added to this Collection.

        Returns True if the FileGroup is valid for this collection:
        - If directory-restricted, the file must be in the directory tree
        - Otherwise, any file is valid
        """
        if not self.is_directory_restricted:
            return True

        # Check if the file_group's primary_path is within the collection's directory
        try:
            file_path = file_group.primary_path
            if file_path:
                # Check if file is in directory tree
                file_path.relative_to(self.directory)
                return True
        except (ValueError, AttributeError):
            # relative_to raises ValueError if path is not relative
            return False

        return False

    def add_file_group(self, file_group: FileGroup, position: Optional[int] = None,
                       session: Session = None) -> 'CollectionItem':
        """
        Add a FileGroup to this Collection.

        Args:
            file_group: The FileGroup to add
            position: Optional position in the collection (None = append to end)
            session: Database session

        Returns:
            The created CollectionItem

        Raises:
            ValueError: If the file_group cannot be added to this collection
        """
        session = session or Session.object_session(self)

        if not self.validate_file_group(file_group):
            raise ValueError(
                f'FileGroup {file_group.id} at {file_group.primary_path} '
                f'cannot be added to collection "{self.name}" (directory restriction: {self.directory})'
            )

        # Check if already exists
        existing = session.query(CollectionItem).filter_by(
            collection_id=self.id,
            file_group_id=file_group.id
        ).first()

        if existing:
            logger.warning(f'FileGroup {file_group.id} already in Collection {self.id}')
            return existing

        # Determine position
        if position is None:
            # Append to end
            max_position = session.query(func.max(CollectionItem.position)).filter_by(
                collection_id=self.id
            ).scalar()
            position = (max_position or 0) + 1
        else:
            # Insert at specific position - need to shift existing items
            self._shift_positions(session, position, shift_by=1)

        item = CollectionItem(
            collection_id=self.id,
            file_group_id=file_group.id,
            position=position
        )
        session.add(item)
        session.flush([item])

        return item

    def add_file_groups(self, session: Session, file_groups: List[FileGroup]) -> List['CollectionItem']:
        """
        Add multiple FileGroups to this Collection in batch.
        More efficient than calling add_file_group in a loop.

        Args:
            session: Database session
            file_groups: List of FileGroups to add

        Returns:
            List of created CollectionItems
        """

        # Validate all file groups first
        for fg in file_groups:
            if not self.validate_file_group(fg):
                raise ValueError(
                    f'FileGroup {fg.id} at {fg.primary_path} '
                    f'cannot be added to collection "{self.name}" (directory restriction: {self.directory})'
                )

        # Get existing items to avoid duplicates
        existing_fg_ids = {item.file_group_id for item in self.items}
        new_file_groups = [fg for fg in file_groups if fg.id not in existing_fg_ids]

        if not new_file_groups:
            logger.debug(f'All FileGroups already in Collection {self.id}')
            return []

        # Get starting position
        max_position = session.query(func.max(CollectionItem.position)).filter_by(
            collection_id=self.id
        ).scalar()
        position = (max_position or 0) + 1

        # Create items in batch
        items = []
        for fg in new_file_groups:
            item = CollectionItem(
                collection_id=self.id,
                file_group_id=fg.id,
                position=position
            )
            items.append(item)
            position += 1

        session.add_all(items)
        session.flush(items)

        logger.debug(f'Added {len(items)} FileGroups to Collection {self.id}')
        return items

    def remove_file_group(self, session: Session, file_group_id: int):
        """Remove a FileGroup from this Collection."""

        item = session.query(CollectionItem).filter_by(
            collection_id=self.id,
            file_group_id=file_group_id
        ).first()

        if item:
            position = item.position
            session.delete(item)
            session.flush()

            # Shift remaining items down
            self._shift_positions(session, position + 1, shift_by=-1)

    def remove_file_groups(self, session: Session, file_group_ids: List[int]):
        """
        Remove multiple FileGroups from this Collection in batch.
        More efficient than calling remove_file_group in a loop.

        Args:
            session: Database session
            file_group_ids: List of FileGroup IDs to remove
        """

        if not file_group_ids:
            return

        # Delete all items at once
        deleted = session.query(CollectionItem).filter(
            CollectionItem.collection_id == self.id,
            CollectionItem.file_group_id.in_(file_group_ids)
        ).delete(synchronize_session=False)

        logger.debug(f'Removed {deleted} FileGroups from Collection {self.id}')

        # Resequence positions to close gaps (optional, but keeps positions clean)
        items = session.query(CollectionItem).filter_by(
            collection_id=self.id
        ).order_by(CollectionItem.position).all()

        for idx, item in enumerate(items, start=1):
            item.position = idx

        session.flush(items)

    def reorder_item(self, file_group_id: int, new_position: int, session: Session = None):
        """Move an item to a new position in the collection."""
        session = session or Session.object_session(self)

        item = session.query(CollectionItem).filter_by(
            collection_id=self.id,
            file_group_id=file_group_id
        ).first()

        if not item:
            raise ValueError(f'FileGroup {file_group_id} not in Collection {self.id}')

        old_position = item.position

        if old_position == new_position:
            return

        # Remove item from old position
        session.query(CollectionItem).filter(
            CollectionItem.collection_id == self.id,
            CollectionItem.position > old_position
        ).update({'position': CollectionItem.position - 1})

        # Make space at new position
        session.query(CollectionItem).filter(
            CollectionItem.collection_id == self.id,
            CollectionItem.position >= new_position
        ).update({'position': CollectionItem.position + 1})

        # Update item position
        item.position = new_position
        session.flush()

    def _shift_positions(self, session: Session, from_position: int, shift_by: int):
        """Helper to shift positions of items."""
        session.query(CollectionItem).filter(
            CollectionItem.collection_id == self.id,
            CollectionItem.position >= from_position
        ).update({'position': CollectionItem.position + shift_by})
        session.flush()

    def get_items(self, session: Session, limit: Optional[int] = None, offset: int = 0) -> List['CollectionItem']:
        """Get items in this collection, ordered by position."""

        query = session.query(CollectionItem).filter_by(
            collection_id=self.id
        ).order_by(CollectionItem.position)

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        return query.all()

    @staticmethod
    def get_by_id(session: Session, id_: int) -> Optional['Collection']:
        """Attempt to find a Collection with the provided id. Returns None if not found."""
        return session.query(Collection).filter_by(id=id_).one_or_none()

    @staticmethod
    def find_by_id(session: Session, id_: int) -> 'Collection':
        """Find a Collection with the provided id, raises an exception if not found.

        @raise UnknownCollection: if the collection cannot be found
        """
        if collection := Collection.get_by_id(session, id_):
            return collection
        raise UnknownCollection(f'Cannot find Collection with id {id_}')

    @staticmethod
    def get_by_path(session: Session, path: pathlib.Path) -> Optional['Collection']:
        """Find a Collection by its directory path. Returns None if not found."""
        if not path:
            return None
        path = pathlib.Path(path) if isinstance(path, str) else path
        path = str(path.absolute()) if path.is_absolute() else str(get_media_directory() / path)
        return session.query(Collection).filter_by(directory=path).one_or_none()

    @staticmethod
    def find_by_path(session: Session, path: pathlib.Path) -> 'Collection':
        """Find a Collection by its directory path, raises an exception if not found.

        @raise UnknownCollection: if the collection cannot be found
        """
        if collection := Collection.get_by_path(session, path):
            return collection
        raise UnknownCollection(f'Cannot find Collection with directory {path}')

    def dict(self) -> dict:
        """Return dictionary representation."""
        d = super(Collection, self).dict()
        d['tag_name'] = self.tag_name
        # Directory may be outside media root; mirror to_config behavior
        if self.directory:
            try:
                d['directory'] = self.directory.relative_to(get_media_directory())
            except ValueError:
                d['directory'] = self.directory
        else:
            d['directory'] = None
        d['is_directory_restricted'] = self.is_directory_restricted
        d['item_count'] = self.item_count
        d['total_size'] = self.total_size
        d['kind'] = self.kind
        return d

    # --- Tagging and moving helpers ---
    def set_tag(self, tag_id_or_name: int | str | None) -> Optional[Tag]:
        """Assign or clear the Tag on this Collection. Mirrors Channel.set_tag semantics.

        All collections can be tagged regardless of directory status. Tags enable
        UI search/filtering even for directory-less collections.
        """
        session = Session.object_session(self)
        if tag_id_or_name is None:
            self.tag = None
        elif isinstance(tag_id_or_name, int):
            self.tag = Tag.find_by_id(session, tag_id_or_name)
        elif isinstance(tag_id_or_name, str):
            self.tag = Tag.find_by_name(session, tag_id_or_name)
        self.tag_id = self.tag.id if self.tag else None
        return self.tag

    def __json__(self) -> dict:
        """Return JSON-serializable dict for API responses.

        Returns directory as a string relative to media directory if applicable.
        """
        # Get directory as string, relative to media directory
        directory_str = None
        if self.directory:
            try:
                directory_str = str(get_relative_to_media_directory(self.directory))
            except ValueError:
                # Directory is not relative to media directory, return as-is
                directory_str = str(self.directory)

        return {
            'id': self.id,
            'name': self.name,
            'kind': self.kind,
            'directory': directory_str,
            'description': self.description,
            'tag_name': self.tag.name if self.tag else None,
            'item_count': self.item_count,
            'total_size': self.total_size,
            'downloads': self.downloads,
        }

    def format_directory(self, tag_name: Optional[str]) -> pathlib.Path:
        """Compute the destination directory for this Collection given a tag name.

        For video-style collections (kind == 'channel'), reuse videos destination formatting:
        videos/<Tag>/<Collection Name>

        For domain collections (kind == 'domain'), use the configured archive directory:
        archive/<Tag>/<Domain Name>

        @deprecated: Use format_destination() instead for new code.
        """
        # Delegate to format_destination for consistency
        return self.format_destination(tag_name)

    def format_destination(self, tag_name: Optional[str] = None) -> pathlib.Path:
        """Format the collection's destination path using config template.

        Uses videos_destination for kind='channel', archive_destination for kind='domain'.
        Supports unified variables that work for both kinds.

        Args:
            tag_name: Optional tag name to include in the path

        Returns:
            Absolute path where this collection's files should be stored
        """
        from wrolpi.common import get_wrolpi_config, escape_file_name

        config = get_wrolpi_config()

        if self.kind == 'channel':
            template = config.videos_destination
        elif self.kind == 'domain':
            template = config.archive_destination
        else:
            template = '%(kind)s/%(tag)s/%(name)s'

        escaped_name = escape_file_name(self.name) if self.name else ''

        variables = dict(
            # Unified variables
            name=escaped_name,
            tag=tag_name or '',
            kind=self.kind or '',
            # Backward compatibility aliases for videos
            channel_name=escaped_name,
            channel_tag=tag_name or '',
            # Backward compatibility aliases for archives
            domain=escaped_name,
            domain_tag=tag_name or '',
        )

        destination = template % variables
        return get_media_directory() / destination.lstrip('/')

    def get_or_set_directory(self, session: Session, tag_name: Optional[str] = None) -> pathlib.Path:
        """Get collection's directory, or format and save it on first use.

        - If collection has directory: return it
        - If no directory: format from template, save to collection, return it

        This ensures all files for a collection go to the same place, even if
        the template config changes later.

        Args:
            session: Database session for committing changes
            tag_name: Optional tag name to use when formatting (defaults to collection's tag)

        Returns:
            Absolute path to the collection's directory
        """
        if self.directory:
            return get_media_directory() / self.directory

        # First use - format and save
        tag_name = tag_name or (self.tag.name if self.tag else None)
        destination = self.format_destination(tag_name)

        self.directory = get_relative_to_media_directory(destination)
        session.commit()

        # Trigger config save for persistence
        if self.kind == 'domain':
            from modules.archive.lib import save_domains_config
            save_domains_config.activate_switch()
        elif self.kind == 'channel':
            from modules.videos.lib import save_channels_config
            save_channels_config.activate_switch()

        return destination

    async def move_collection(self, directory: pathlib.Path, session: Session, send_events: bool = False,
                              with_files: bool = True):
        """Move all files under this Collection's directory to a new directory.

        Also updates download destinations for downloads associated with this collection.

        If with_files=False, only updates the directory reference without moving files.
        Use this when files have already been moved by a parent directory rename.
        """
        if not directory.is_dir():
            raise FileNotFoundError(f'Destination directory does not exist: {directory}')

        if not self.directory:
            raise RuntimeError('Cannot move an unrestricted Collection (no directory set)')

        old_directory = self.directory

        def change_download_destinations(from_directory: pathlib.Path, to_directory: pathlib.Path):
            """Update download destinations from one directory to another."""
            downloads = list(self.downloads)
            downloads.extend(Download.get_all_by_destination(session, from_directory))
            downloads = unique_by_predicate(downloads, lambda i: i.id)
            if __debug__ and logger.isEnabledFor(TRACE_LEVEL):
                logger.trace(f'move_collection: updating {len(downloads)} download destinations')
            for download in downloads:
                download.destination = to_directory
            session.flush(downloads)

        self.directory = directory

        with flags.refreshing:
            # Update download destinations before moving files.
            change_download_destinations(old_directory, directory)
            session.commit()
            # Move the contents of the Collection directory into the destination directory.
            logger.info(f'Moving Collection {repr(self.name)} from {repr(str(old_directory))}')
            # Save configs before move - move triggers imports of configs.
            save_downloads_config.activate_switch()
            save_tags_config.activate_switch()

        if with_files:
            try:
                if not old_directory.exists():
                    # Old directory does not exist; refresh both
                    await refresh_files([old_directory, directory])
                    if send_events:
                        Events.send_file_move_completed(f'Collection {repr(self.name)} was moved (directory missing)')
                else:
                    files_to_move = list(old_directory.iterdir())
                    if __debug__ and logger.isEnabledFor(TRACE_LEVEL):
                        logger.trace(f'move_collection: moving {len(files_to_move)} items from {old_directory}')
                    await move_files(session, directory, *files_to_move)
                    if send_events:
                        Events.send_file_move_completed(f'Collection {repr(self.name)} was moved')
            except Exception as e:
                logger.error(f'Collection move failed! Reverting changes...', exc_info=e)
                # Revert download destinations
                change_download_destinations(directory, old_directory)
                self.directory = old_directory
                self.flush(session)
                if send_events:
                    Events.send_file_move_failed(f'Moving Collection {self.name} has failed')
                raise
            finally:
                session.commit()
                if old_directory.exists() and not next(iter(old_directory.iterdir()), None):
                    old_directory.rmdir()
        else:
            # Files already moved, just send event
            if send_events:
                Events.send_file_move_completed(f'Collection {repr(self.name)} directory updated')


class CollectionItem(ModelHelper, Base):
    """
    Junction table between Collection and FileGroup.
    Maintains ordering and metadata about the relationship.
    """
    __tablename__ = 'collection_item'

    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey('collection.id', ondelete='CASCADE'), nullable=False)
    file_group_id = Column(Integer, ForeignKey('file_group.id', ondelete='CASCADE'), nullable=False)

    # Position in the collection (for ordering)
    position = Column(Integer, nullable=False, default=0)

    # When this item was added
    added_date = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    collection = relationship('Collection', back_populates='items')
    file_group: FileGroup = relationship('FileGroup')

    # Indexes for performance
    __table_args__ = (
        Index('idx_collection_item_collection_id', 'collection_id'),
        Index('idx_collection_item_collection_position', 'collection_id', 'position'),
        Index('idx_collection_item_file_group_id', 'file_group_id'),
        Index('idx_collection_item_position', 'position'),
        UniqueConstraint('collection_id', 'file_group_id', name='uq_collection_file_group'),
    )

    def __repr__(self):
        return f'<CollectionItem collection={self.collection_id} file_group={self.file_group_id} position={self.position}>'

    def dict(self) -> dict:
        """Return dictionary representation."""
        d = super(CollectionItem, self).dict()
        if self.file_group:
            d['file_group'] = self.file_group.__json__()
        return d
