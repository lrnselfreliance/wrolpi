"""Test for zim_modeler loop to ensure it processes more than one batch.

This test ensures the zim_modeler can process more than its batch limit (10)
files. If the loop logic has an off-by-one error (like using enumerate() with wrong
comparison), the modeler would only process one batch and exit early.
"""
import shutil

import pytest

from modules.zim.lib import zim_modeler
from modules.zim.models import Zim
from wrolpi.files.models import FileGroup
from wrolpi.vars import PROJECT_DIR

# The zim_modeler uses a hardcoded limit of 10
ZIM_PROCESSING_LIMIT = 10


@pytest.mark.asyncio
async def test_zim_modeler_processes_more_than_batch_limit(async_client, test_session, test_directory):
    """
    Test that zim_modeler processes MORE than the batch limit (10) files.

    This test creates 15 zim files and verifies that zim_modeler
    processes all of them, not just the first batch of 10.

    This catches off-by-one bugs in the loop logic (e.g., using enumerate()
    which is 0-indexed but comparing against the limit incorrectly).
    """
    zim_dir = test_directory / 'zims'
    zim_dir.mkdir(parents=True)

    # Create more zim files than the batch limit
    num_zims = ZIM_PROCESSING_LIMIT + 5  # 15 zims
    zim_paths = []

    for i in range(num_zims):
        zim_path = zim_dir / f'test_zim_{i:03d}.zim'
        shutil.copy(PROJECT_DIR / 'test/zim.zim', zim_path)
        zim_paths.append(zim_path)

    # Create FileGroups for each zim file (simulating what refresh does)
    for zim_path in zim_paths:
        fg = FileGroup.from_paths(test_session, zim_path)
        # Zim files don't have a standard mimetype, they're identified by suffix
        assert fg.primary_path.suffix == '.zim'

    test_session.commit()

    # Verify we have the expected number of FileGroups needing deep indexing
    # Two-phase: indexed=True (surface), deep_indexed=False (needs modeler)
    needs_deep_count = test_session.query(FileGroup).filter(
        FileGroup.indexed == True,
        FileGroup.deep_indexed != True,
        FileGroup.primary_path.ilike('%.zim'),
    ).count()
    assert needs_deep_count == num_zims, f"Expected {num_zims} files needing deep indexing, got {needs_deep_count}"

    # Run the zim_modeler
    await zim_modeler()

    # Count how many Zims were created
    zim_count = test_session.query(Zim).count()

    # All zims should be created
    assert zim_count == num_zims, \
        f"zim_modeler should process ALL {num_zims} files, but only processed {zim_count}. " \
        f"This may be an off-by-one bug in the loop logic!"

    # Also verify all FileGroups are now deep indexed
    still_needs_deep = test_session.query(FileGroup).filter(
        FileGroup.indexed == True,
        FileGroup.deep_indexed != True,
        FileGroup.primary_path.ilike('%.zim'),
    ).count()
    assert still_needs_deep == 0, \
        f"All zim FileGroups should be deep indexed, but {still_needs_deep} remain"
