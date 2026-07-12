from logging.config import fileConfig

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from wrolpi.common import Base
# Import all models so they are registered with the Base metadata
from wrolpi.files.models import FileGroup, Directory  # noqa: F401
from modules.docs.models import Doc  # noqa: F401
from wrolpi.tags import Tag  # noqa: F401
from wrolpi.flags import WROLPiFlag  # noqa: F401
from wrolpi.downloader import Download  # noqa: F401
from wrolpi.collections.models import Collection, CollectionItem  # noqa: F401
from modules.videos.models import Video, Channel  # noqa: F401
from modules.archive.models import Archive  # noqa: F401
from modules.zim.models import Zim, TagZimEntry, ZimSubscription  # noqa: F401

target_metadata = Base.metadata


def get_url() -> str:
    """The database URL: from the ini/CLI when overridden, otherwise derived from the media directory."""
    url = config.get_main_option('sqlalchemy.url')
    if url and not url.startswith('sqlite:///CHANGEME'):
        return url
    from wrolpi.db import get_db_uri
    return get_db_uri()


def include_object(object_, name, type_, reflected, compare_to):
    """Exclude tables Alembic must not manage from autogenerate/check.

    The FTS5 virtual tables and their shadow tables (created by wrolpi.schema_ddl /
    wrolpi.fts) plus SQLite internals would otherwise be proposed for DROP."""
    if type_ == 'table':
        from wrolpi.fts import FTS_TABLE_PREFIXES
        if name == 'sqlite_sequence' or any(name.startswith(prefix) for prefix in FTS_TABLE_PREFIXES):
            return False
    return True


def process_revision_directives(context_, revision, directives):
    """New revisions get date ids (e.g. 2026_07_10_1350) instead of random hashes.

    Filenames therefore self-sort chronologically, and the `alembic_version` value in a
    database says when its schema was created.  Underscores, not dashes: alembic forbids
    `-` in revision identifiers (it is reserved for relative-revision syntax like `head-1`)."""
    from datetime import datetime, timezone
    script = directives[0]
    script.rev_id = datetime.now(timezone.utc).strftime('%Y_%m_%d_%H%M')


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        include_object=include_object,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    from wrolpi.db import create_wrolpi_engine

    connectable = create_wrolpi_engine(get_url())

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite's limited ALTER TABLE requires batch mode for most column changes.
            render_as_batch=True,
            include_object=include_object,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
