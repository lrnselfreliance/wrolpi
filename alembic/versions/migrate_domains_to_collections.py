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
from typing import Dict, List
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'migrate_domains_to_collections'
down_revision = '66407d145b76'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


class DomainMigrationStats:
    """Track migration statistics."""
    def __init__(self):
        self.domains_found = 0
        self.domains_migrated = 0
        self.collections_created = 0
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
        print(f"Domains found:           {self.domains_found}")
        print(f"Domains migrated:        {self.domains_migrated}")
        print(f"Collections created:     {self.collections_created}")
        print(f"CollectionItems created: {self.collection_items_created}")
        print(f"Archives linked:         {self.archives_linked}")

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


def perform_domain_migration(session: Session, verbose: bool = True) -> DomainMigrationStats:
    """
    Migrate all Domain records to Collection records.

    This function is integrated into the alembic migration.
    """
    from wrolpi.collections import Collection, CollectionItem

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

        # Check if Collection already exists
        existing = session.query(Collection).filter_by(
            name=domain_name,
            kind='domain'
        ).first()

        if existing:
            stats.add_warning(f"Collection already exists for domain {repr(domain_name)} (id={existing.id})")
            domain_to_collection[domain_id] = existing.id
            stats.domains_migrated += 1
            continue

        # Create Collection
        collection = Collection(
            name=domain_name,
            kind='domain',
            directory=None,  # Domains are unrestricted
        )
        session.add(collection)
        session.flush([collection])

        domain_to_collection[domain_id] = collection.id
        stats.collections_created += 1
        stats.domains_migrated += 1

        if verbose:
            print(f"    Created Collection id={collection.id}")

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

            # Check if CollectionItem already exists
            existing_item = session.query(CollectionItem).filter_by(
                collection_id=collection_id,
                file_group_id=file_group_id
            ).first()

            if existing_item:
                if verbose:
                    print(f"    Archive {archive_id} already linked to collection")
                continue

            # Create CollectionItem
            item = CollectionItem(
                collection_id=collection_id,
                file_group_id=file_group_id,
                position=idx
            )
            session.add(item)
            stats.collection_items_created += 1

    session.flush()
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
