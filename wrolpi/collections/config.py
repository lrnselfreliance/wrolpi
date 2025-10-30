import pathlib
from dataclasses import dataclass, field
from typing import List

from wrolpi.common import ConfigFile, logger
from wrolpi.db import get_db_session
from wrolpi.events import Events
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod

logger = logger.getChild(__name__)

__all__ = ['CollectionsConfig', 'collections_config', 'save_collections_config']


@dataclass
class CollectionsConfigValidator:
    """Validator for collections config file."""
    version: int = 0
    collections: List[dict] = field(default_factory=list)


class CollectionsConfig(ConfigFile):
    """
    Config file for Collections.

    This config stores Collection metadata (name, description, directory, tag)
    but NOT the individual items. Items are stored in the database.

    For directory-restricted collections, items are auto-populated from the directory.
    For unrestricted collections, items are managed manually through the API.

    Format:
        collections:
          - name: "My Videos"
            description: "Favorite videos"
            directory: "videos/favorites"  # optional, enables auto-population
            tag_name: "favorites"  # optional
          - name: "Reading List"
            description: "Books to read"
            # No directory means manual item management
    """
    file_name = 'collections.yaml'
    validator = CollectionsConfigValidator
    default_config = dict(
        version=0,
        collections=[],
    )
    # Use wider width to accommodate longer paths
    width = 120

    def __getitem__(self, item):
        return self._config[item]

    def __setitem__(self, key, value):
        self._config[key] = value

    @property
    def collections(self) -> List[dict]:
        """Get list of collection configs."""
        return self._config.get('collections', [])

    def import_config(self, file: pathlib.Path = None, send_events=False):
        """Import collections from config file into database."""
        from .models import Collection

        super().import_config(file, send_events)

        file_str = str(self.get_relative_file())
        collections_data = self._config.get('collections', [])

        if not collections_data:
            logger.info(f'No collections to import from {file_str}')
            self.successful_import = True
            return

        logger.info(f'Importing {len(collections_data)} collections from {file_str}')

        try:
            with get_db_session(commit=True) as session:
                # Track which collections were imported
                imported_dirs = set()  # absolute paths for directory-restricted collections
                imported_pairs = set()  # (name, kind) for unrestricted collections

                # Import each collection using from_config
                for idx, collection_data in enumerate(collections_data):
                    try:
                        name = collection_data.get('name')
                        if not name:
                            logger.error(f'Collection at index {idx} has no name, skipping')
                            continue

                        # Use Collection.from_config to create/update
                        # This will auto-populate items if directory exists
                        collection = Collection.from_config(collection_data, session)

                        if collection.directory:
                            # Normalize to absolute string for comparison
                            imported_dirs.add(str(collection.directory))
                        else:
                            imported_pairs.add((collection.name, collection.kind))

                    except Exception as e:
                        logger.error(f'Failed to import collection at index {idx}', exc_info=e)
                        continue

                # Delete collections that are no longer in config
                all_collections = session.query(Collection).all()
                for collection in all_collections:
                    if collection.directory:
                        if str(collection.directory) not in imported_dirs:
                            logger.info(
                                f'Deleting collection {repr(collection.name)} at {collection.directory} (no longer in config)')
                            session.delete(collection)
                    else:
                        if (collection.name, collection.kind) not in imported_pairs:
                            logger.info(
                                f"Deleting unrestricted collection {repr(collection.name)} kind={collection.kind} (no longer in config)")
                            session.delete(collection)

            total_imported = len(imported_dirs) + len(imported_pairs)
            logger.info(f'Successfully imported {total_imported} collections from {file_str}')
            self.successful_import = True

        except Exception as e:
            self.successful_import = False
            message = f'Failed to import {file_str} config!'
            logger.error(message, exc_info=e)
            if send_events:
                Events.send_config_import_failed(message)
            raise

    def dump_config(self, file: pathlib.Path = None, send_events=False, overwrite=False):
        """Dump all collections from database to config file."""
        from .models import Collection

        logger.info('Dumping collections to config')

        with get_db_session() as session:
            # Order by name for consistency
            collections = session.query(Collection).order_by(Collection.name).all()

            # Use to_config to export each collection
            collections_data = [collection.to_config() for collection in collections]

            self._config['collections'] = collections_data

        logger.info(f'Dumping {len(collections_data)} collections to config')
        self.save(file, send_events, overwrite)


# Global instance
collections_config = CollectionsConfig()


# Switch handler for saving collections config
@register_switch_handler('save_collections_config')
def save_collections_config():
    """Save the collections config when the switch is activated."""
    collections_config.background_dump.activate_switch()


# Explicit type for activate_switch helper
save_collections_config: ActivateSwitchMethod
