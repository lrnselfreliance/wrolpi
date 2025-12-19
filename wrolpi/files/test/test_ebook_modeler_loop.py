"""Test for ebook_modeler loop to ensure it processes more than one batch.

This test ensures the ebook_modeler can process more than its batch limit (10)
files. If the loop logic has an off-by-one error (like using enumerate() with wrong
comparison), the modeler would only process one batch and exit early.
"""
import shutil

import pytest

from wrolpi.files.ebooks import ebook_modeler, EBook
from wrolpi.files.models import FileGroup
from wrolpi.vars import PROJECT_DIR

# The ebook_modeler uses a hardcoded limit of 10
EBOOK_PROCESSING_LIMIT = 10


@pytest.mark.asyncio
async def test_ebook_modeler_processes_more_than_batch_limit(async_client, test_session, test_directory):
    """
    Test that ebook_modeler processes MORE than the batch limit (10) files.

    This test creates 15 ebook files and verifies that ebook_modeler
    processes all of them, not just the first batch of 10.

    This catches off-by-one bugs in the loop logic (e.g., using enumerate()
    which is 0-indexed but comparing against the limit incorrectly).
    """
    ebook_dir = test_directory / 'ebooks'
    ebook_dir.mkdir(parents=True)

    # Create more ebooks than the batch limit
    num_ebooks = EBOOK_PROCESSING_LIMIT + 5  # 15 ebooks
    ebook_paths = []

    for i in range(num_ebooks):
        ebook_path = ebook_dir / f'test_ebook_{i:03d}.epub'
        shutil.copy(PROJECT_DIR / 'test/ebook example.epub', ebook_path)
        ebook_paths.append(ebook_path)

    # Create FileGroups for each ebook file (simulating what refresh does)
    for ebook_path in ebook_paths:
        fg = FileGroup.from_paths(test_session, ebook_path)
        # EPUB mimetype might be 'application/epub+zip' or 'application/epub'
        assert fg.mimetype.startswith('application/epub')

    test_session.commit()

    # Verify we have the expected number of unindexed ebook FileGroups
    unindexed_count = test_session.query(FileGroup).filter(
        FileGroup.indexed == False,
        FileGroup.mimetype == 'application/epub+zip',
    ).count()
    assert unindexed_count == num_ebooks, f"Expected {num_ebooks} unindexed ebook files, got {unindexed_count}"

    # Run the ebook_modeler
    await ebook_modeler()

    # Count how many EBooks were created
    ebook_count = test_session.query(EBook).count()

    # All ebooks should be created
    assert ebook_count == num_ebooks, \
        f"ebook_modeler should process ALL {num_ebooks} files, but only processed {ebook_count}. " \
        f"This may be an off-by-one bug in the loop logic!"

    # Also verify all FileGroups are now indexed
    still_unindexed = test_session.query(FileGroup).filter(
        FileGroup.indexed == False,
        FileGroup.mimetype == 'application/epub+zip',
    ).count()
    assert still_unindexed == 0, \
        f"All ebook FileGroups should be indexed, but {still_unindexed} remain unindexed"
