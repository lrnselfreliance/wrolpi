"""Migrate Domain model to Collection model

This migration:
1. Adds collection_id column to archive table
2. Runs the data migration to populate collections
3. Makes collection_id NOT NULL
4. Drops the old domain_id column and domains table

Revision ID: migrate_domains_to_collections
Revises: 66407d145b76
Create Date: 2025-10-29

"""
import os
import pathlib
from typing import Dict, List, Optional
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'migrate_domains_to_collections'
down_revision = '66407d145b76'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False

# Local model definitions for migration stability.
# These are minimal copies of the Collection and CollectionItem models
# that contain only the columns needed for this migration.
# This ensures the migration will work regardless of future changes to the actual models.
MBase = declarative_base()


class MCollection(MBase):
    """Migration-stable Collection model with minimum required columns."""
    __tablename__ = 'collection'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False, server_default='channel', default='channel')
    directory = Column(String, nullable=True)


class MCollectionItem(MBase):
    """Migration-stable CollectionItem model with minimum required columns.

    Note: ForeignKey constraints are NOT declared here because they reference
    tables (file_group) that are not in this migration's declarative base.
    The actual FK constraints exist in the database schema.
    """
    __tablename__ = 'collection_item'

    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, nullable=False)
    file_group_id = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False, default=0)


class DomainMigrationStats:
    """Track migration statistics."""
    def __init__(self):
        self.domains_found = 0
        self.domains_migrated = 0
        self.domains_skipped = 0
        self.collections_created = 0
        self.collections_with_directory = 0
        self.collection_items_created = 0
        self.archives_linked = 0
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_error(self, msg: str):
        self.errors.append(msg)
        print(f"  ✗ ERROR: {msg}")

    def add_warning(self, msg: str):
        self.warnings.append(msg)
        print(f"  ⚠ WARNING: {msg}")

    def print_summary(self, dry_run: bool = False):
        """Print migration summary."""
        mode = "DRY-RUN" if dry_run else "ACTUAL"
        print(f"\n{'='*60}")
        print(f"Domain → Collection Migration Summary ({mode})")
        print(f"{'='*60}")
        print(f"Domains found:              {self.domains_found}")
        print(f"Domains migrated:           {self.domains_migrated}")
        print(f"Domains skipped (no archives): {self.domains_skipped}")
        print(f"Collections created:        {self.collections_created}")
        print(f"Collections with directory: {self.collections_with_directory}")
        print(f"CollectionItems created:    {self.collection_items_created}")
        print(f"Archives linked:            {self.archives_linked}")

        if self.warnings:
            print(f"\nWarnings: {len(self.warnings)}")
            for warning in self.warnings:
                print(f"  ⚠ {warning}")

        if self.errors:
            print(f"\nErrors: {len(self.errors)}")
            for error in self.errors:
                print(f"  ✗ {error}")

        if not self.errors:
            print(f"\n✓ Migration completed successfully")
        else:
            print(f"\n✗ Migration completed with {len(self.errors)} errors")

        print(f"{'='*60}\n")


def get_domain_data(session: Session) -> List[Dict]:
    """Fetch all Domain records from database."""
    result = session.execute(text("SELECT id, domain, directory FROM domains ORDER BY domain"))
    domains = []
    for row in result:
        domains.append({
            'id': row[0],
            'domain': row[1],
            'directory': row[2],
        })
    return domains


def get_archives_for_domain(session: Session, domain_id: int) -> List[Dict]:
    """Get all Archive IDs for a given domain."""
    result = session.execute(
        text("SELECT id, file_group_id FROM archive WHERE domain_id = :domain_id"),
        {'domain_id': domain_id}
    )
    archives = []
    for row in result:
        if row[1]:  # file_group_id must not be null
            archives.append({
                'archive_id': row[0],
                'file_group_id': row[1],
            })
    return archives


def validate_domain_name(domain: str) -> bool:
    """Validate domain name format - must contain at least one dot."""
    if not domain or not isinstance(domain, str):
        return False
    if domain.startswith('.') or domain.endswith('.'):
        return False
    return '.' in domain


def detect_common_directory_from_archives(session: Session, domain_id: int) -> Optional[str]:
    """
    Detect the common directory for all archives belonging to a domain.

    Returns the directory path as a string, or None if no common directory exists.
    """
    result = session.execute(
        text("""
            SELECT fg.primary_path
            FROM archive a
            JOIN file_group fg ON a.file_group_id = fg.id
            WHERE a.domain_id = :domain_id AND fg.primary_path IS NOT NULL
        """),
        {'domain_id': domain_id}
    )

    paths = [pathlib.Path(row[0]) for row in result if row[0]]

    if not paths:
        return None

    # Find common ancestor directory
    common_dir = paths[0].parent

    for path in paths[1:]:
        while common_dir != common_dir.parent:  # Stop at root
            try:
                path.relative_to(common_dir)
                break
            except ValueError:
                common_dir = common_dir.parent

        if common_dir == common_dir.parent:
            return None  # Reached root, no common directory

    return str(common_dir)


def check_directory_conflict(session: Session, directory: str) -> bool:
    """Check if a directory is already used by an existing Collection."""
    result = session.execute(
        text("SELECT id FROM collection WHERE directory = :directory"),
        {'directory': directory}
    )
    return result.first() is not None


def perform_domain_migration(session: Session, verbose: bool = True) -> DomainMigrationStats:
    """
    Migrate all Domain records to Collection records.

    This function is integrated into the alembic migration.
    Uses local MCollection model for migration stability, and raw SQL for
    CollectionItem operations to avoid FK resolution issues with file_group.
    """
    stats = DomainMigrationStats()

    # Step 1: Fetch all domains
    print("Step 1: Fetching Domain records...")
    domains = get_domain_data(session)
    stats.domains_found = len(domains)
    print(f"Found {len(domains)} Domain records")

    if not domains:
        print("No domains to migrate")
        return stats

    # Step 2: Create Collections from Domains
    print("\nStep 2: Creating Collection records...")
    domain_to_collection: Dict[int, int] = {}  # domain_id -> collection_id

    for domain in domains:
        domain_id = domain['id']
        domain_name = domain['domain']

        if verbose:
            print(f"  Processing Domain {domain_id}: {domain_name}")

        # Validate domain name
        if not validate_domain_name(domain_name):
            stats.add_error(f"Invalid domain name: {repr(domain_name)} (skipping)")
            continue

        # Skip domains with no archives - don't create empty collections
        archives = get_archives_for_domain(session, domain_id)
        if not archives:
            if verbose:
                print(f"    Skipping domain {repr(domain_name)} - no archives")
            stats.domains_skipped += 1
            continue

        # Check if Collection already exists
        existing = session.query(MCollection).filter_by(
            name=domain_name,
            kind='domain'
        ).first()

        if existing:
            stats.add_warning(f"Collection already exists for domain {repr(domain_name)} (id={existing.id})")
            domain_to_collection[domain_id] = existing.id
            stats.domains_migrated += 1
            continue

        # Determine directory for the collection
        directory = None

        # Step 1: Check if Domain.directory is set
        domain_directory = domain.get('directory')
        if domain_directory:
            directory = domain_directory
            if verbose:
                print(f"    Using Domain.directory: {directory}")
        else:
            # Step 2: Detect common directory from archive file paths
            detected = detect_common_directory_from_archives(session, domain_id)
            if detected:
                directory = detected
                if verbose:
                    print(f"    Detected directory from archives: {directory}")

        # Step 3: Check for directory conflicts
        if directory and check_directory_conflict(session, directory):
            stats.add_warning(
                f"Directory {repr(directory)} already used by another Collection "
                f"(domain {repr(domain_name)} will have no directory)"
            )
            directory = None

        # Create Collection
        collection = MCollection(
            name=domain_name,
            kind='domain',
            directory=directory,
        )
        session.add(collection)
        session.flush([collection])

        domain_to_collection[domain_id] = collection.id
        stats.collections_created += 1
        stats.domains_migrated += 1
        if directory:
            stats.collections_with_directory += 1

        if verbose:
            if directory:
                print(f"    Created Collection id={collection.id} with directory={directory}")
            else:
                print(f"    Created Collection id={collection.id} (no directory)")

    print(f"Created {stats.collections_created} Collection records")

    # Step 3: Update archive.collection_id for all Archives
    print("\nStep 3: Updating archive.collection_id...")

    for domain in domains:
        domain_id = domain['id']
        domain_name = domain['domain']

        if domain_id not in domain_to_collection:
            # Domain was skipped due to error
            continue

        collection_id = domain_to_collection[domain_id]

        # Update all archives for this domain
        result = session.execute(
            text("UPDATE archive SET collection_id = :collection_id WHERE domain_id = :domain_id"),
            {'collection_id': collection_id, 'domain_id': domain_id}
        )
        updated_count = result.rowcount

        if verbose and updated_count > 0:
            print(f"  Domain {repr(domain_name)}: Updated {updated_count} archives")

        stats.archives_linked += updated_count

    print(f"Updated {stats.archives_linked} Archives with collection_id")

    # Step 3b: Handle orphan archives (those with NULL domain_id) by creating collections from their URLs
    print("\nStep 3b: Handling orphan archives (NULL domain_id)...")
    result = session.execute(text("""
        SELECT a.id, a.file_group_id, fg.url
        FROM archive a
        LEFT JOIN file_group fg ON a.file_group_id = fg.id
        WHERE a.domain_id IS NULL
    """))
    orphans = list(result)
    if orphans:
        print(f"  Found {len(orphans)} orphan archives:")

        # Group orphans by domain extracted from URL
        from urllib.parse import urlparse
        domain_orphans = {}
        for archive_id, file_group_id, url in orphans:
            print(f"    Archive {archive_id}: {url}")
            try:
                parsed = urlparse(url)
                domain = parsed.netloc
                if domain.startswith('www.'):
                    domain = domain[4:]
            except Exception:
                domain = 'unknown.domain'

            if domain not in domain_orphans:
                domain_orphans[domain] = []
            domain_orphans[domain].append((archive_id, file_group_id))

        # Create collections for each domain and assign orphans
        for domain_name, archives in domain_orphans.items():
            print(f"  Creating collection for domain: {domain_name} ({len(archives)} archives)")

            # Check if collection already exists
            existing = session.execute(
                text("SELECT id FROM collection WHERE name = :name AND kind = 'domain'"),
                {'name': domain_name}
            ).first()

            if existing:
                collection_id = existing[0]
                print(f"    Using existing collection id={collection_id}")
            else:
                # Create new collection
                session.execute(
                    text("INSERT INTO collection (name, kind) VALUES (:name, 'domain')"),
                    {'name': domain_name}
                )
                collection_id = session.execute(text("SELECT lastval()")).scalar()
                stats.collections_created += 1
                print(f"    Created collection id={collection_id}")

            # Update archives with collection_id and create CollectionItems
            for archive_id, file_group_id in archives:
                session.execute(
                    text("UPDATE archive SET collection_id = :collection_id WHERE id = :archive_id"),
                    {'collection_id': collection_id, 'archive_id': archive_id}
                )
                stats.archives_linked += 1

                # Create CollectionItem if not exists
                existing_item = session.execute(
                    text("SELECT id FROM collection_item WHERE collection_id = :cid AND file_group_id = :fgid"),
                    {'cid': collection_id, 'fgid': file_group_id}
                ).first()
                if not existing_item:
                    session.execute(
                        text("INSERT INTO collection_item (collection_id, file_group_id, position) VALUES (:cid, :fgid, 0)"),
                        {'cid': collection_id, 'fgid': file_group_id}
                    )
                    stats.collection_items_created += 1

        print(f"  Processed {len(orphans)} orphan archives into {len(domain_orphans)} collections")
    else:
        print("  No orphan archives found")

    # Step 4: Create CollectionItem records
    print("\nStep 4: Creating CollectionItem records...")

    for domain in domains:
        domain_id = domain['id']
        domain_name = domain['domain']

        if domain_id not in domain_to_collection:
            continue

        collection_id = domain_to_collection[domain_id]

        # Get all archives for this domain
        archives = get_archives_for_domain(session, domain_id)

        if not archives:
            if verbose:
                print(f"  Domain {repr(domain_name)}: No archives found")
            continue

        if verbose:
            print(f"  Domain {repr(domain_name)}: {len(archives)} archives")

        for idx, archive in enumerate(archives, start=1):
            file_group_id = archive['file_group_id']
            archive_id = archive['archive_id']

            # Check if CollectionItem already exists (use raw SQL to avoid FK resolution issues)
            result = session.execute(
                text("SELECT id FROM collection_item WHERE collection_id = :collection_id AND file_group_id = :file_group_id"),
                {'collection_id': collection_id, 'file_group_id': file_group_id}
            )
            existing_item = result.first()

            if existing_item:
                if verbose:
                    print(f"    Archive {archive_id} already linked to collection")
                continue

            # Create CollectionItem (use raw SQL to avoid FK resolution issues)
            session.execute(
                text("INSERT INTO collection_item (collection_id, file_group_id, position) VALUES (:collection_id, :file_group_id, :position)"),
                {'collection_id': collection_id, 'file_group_id': file_group_id, 'position': idx}
            )
            stats.collection_items_created += 1
    print(f"Created {stats.collection_items_created} CollectionItem records")

    # Step 5: Skip config export during migration
    # The config export requires a separate database session, but we're inside
    # an alembic transaction. The application will export on startup instead.
    print("\nStep 5: Skipping domains.yaml export during migration...")
    print("  (Config will be exported on next application startup)")

    return stats


def upgrade():
    """
    Migrate Domains to Collections.

    This is a one-way migration - there is no downgrade path because:
    - Domain data is transformed into Collection data
    - Once migrated, the system uses Collections exclusively
    - Downgrade would require reimplementing Domain model
    """
    bind = op.get_bind()
    session = Session(bind=bind)

    print("\n" + "="*60)
    print("DOMAIN → COLLECTION MIGRATION")
    print("="*60 + "\n")

    # Step 1: Add collection_id column to archive table (nullable initially)
    print("Step 1: Adding collection_id column to archive table...")
    op.add_column('archive',
                  sa.Column('collection_id', sa.Integer(), nullable=True))

    # Add foreign key to collection table
    op.create_foreign_key(
        'archive_collection_id_fkey',
        'archive', 'collection',
        ['collection_id'], ['id'],
        ondelete='CASCADE'
    )
    print("✓ Added collection_id column\n")

    # Step 2: Run data migration script
    print("Step 2: Running data migration script...")
    print("This will:")
    print("  - Create Collection records from Domain records")
    print("  - Create CollectionItem records for Archives\n")

    try:
        # Commit the schema changes before running migration
        session.commit()

        # Run the data migration
        stats = perform_domain_migration(session, verbose=True)

        # Print summary
        stats.print_summary(dry_run=False)

        if stats.errors:
            raise Exception(f"Migration completed with {len(stats.errors)} errors. See logs above.")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        raise

    # Step 3: Make collection_id NOT NULL
    print("\nStep 3: Making collection_id NOT NULL...")

    # Check if any archives don't have a collection_id
    result = session.execute(sa.text(
        "SELECT COUNT(*) FROM archive WHERE collection_id IS NULL"
    ))
    null_count = result.scalar()

    if null_count > 0:
        raise Exception(
            f"Cannot make collection_id NOT NULL: {null_count} archives have NULL collection_id. "
            f"The migration script should have assigned all archives to collections."
        )

    op.alter_column('archive', 'collection_id', nullable=False)
    print("✓ collection_id is now NOT NULL\n")

    # Step 4: Drop old domain_id column and foreign key
    print("Step 4: Dropping domain_id column and foreign key...")
    op.drop_constraint('archive_domain_id_fkey', 'archive', type_='foreignkey')
    op.drop_column('archive', 'domain_id')
    print("✓ Dropped domain_id column\n")

    # Step 5: Drop domains table
    print("Step 5: Dropping domains table...")
    op.drop_table('domains')
    print("✓ Dropped domains table\n")

    # Ensure table ownership in non-docker environments
    if not DOCKERIZED:
        print("Setting table ownership...")
        session.execute(sa.text('ALTER TABLE public.archive OWNER TO wrolpi'))
        session.commit()

    print("="*60)
    print("MIGRATION COMPLETED SUCCESSFULLY")
    print("="*60 + "\n")


def downgrade():
    """
    No downgrade path for this migration.

    This is intentional because:
    1. Domain → Collection is a one-way data transformation
    2. The Domain model is being removed from the codebase
    3. Rolling back would require:
       - Recreating Domain model code
       - Reversing the data transformation (Collection → Domain)
       - Handling edge cases where Collections have features Domains didn't

    If you need to rollback, you should:
    1. Restore from a database backup taken before migration
    2. Re-index all files to rebuild Domain records
    """
    raise NotImplementedError(
        "This migration has no downgrade path. "
        "To rollback, reset database and re-index files."
    )
