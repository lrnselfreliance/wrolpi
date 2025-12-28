"""Test for archive_modeler loop bug.

The bug: archive_modeler uses enumerate() which is 0-indexed, but checks
`if processed < 20` to determine if more batches exist. After processing
exactly 20 items, processed=19, so 19 < 20 is True and the loop exits early.

This means archive_modeler only ever processes ONE batch of 20 files,
leaving all other archives unprocessed.
"""
import datetime
import pathlib

import pytest
import pytz

from modules.archive import archive_modeler
from modules.archive.lib import archive_strftime
from modules.archive.models import Archive
from wrolpi.files.models import FileGroup


def create_singlefile_content(url: str, title: str) -> str:
    """Create minimal singlefile HTML content with embedded URL."""
    return f'''<!DOCTYPE html><html><!--
 Page saved with SingleFile
 url: {url}
 saved date: Mon May 16 2022 23:51:35 GMT+0000 (Coordinated Universal Time)
--><head><meta charset="utf-8">
<meta name="generator" content="SingleFile">
<title>{title}</title>
</head>
<body><h1>{title}</h1><p>Content</p></body>
</html>'''


@pytest.mark.asyncio
async def test_archive_modeler_processes_more_than_20_files(async_client, test_session, test_directory,
                                                             make_files_structure):
    """
    Test that archive_modeler processes MORE than 20 files.

    This test creates 25 singlefile archives and verifies that archive_modeler
    processes all of them, not just the first batch of 20.

    The bug: enumerate() is 0-indexed, so after processing 20 items,
    processed=19. The check `if processed < 20` is True (19 < 20), causing
    the loop to exit after just one batch.
    """
    domain = 'example.com'
    archive_dir = test_directory / 'archives' / domain
    archive_dir.mkdir(parents=True)

    # Create 25 singlefile archives (more than one batch of 20)
    num_archives = 25
    files_structure = {}

    for i in range(num_archives):
        # Use different days to avoid hour overflow
        timestamp = archive_strftime(
            datetime.datetime(2000, 1, 1 + i, 0, 0, 0).astimezone(pytz.UTC)
        )
        title = f'Article {i}'
        url = f'https://{domain}/article-{i}'

        singlefile_content = create_singlefile_content(url, title)
        html_path = str(archive_dir / f'{timestamp}_{title}.html')
        files_structure[html_path] = singlefile_content

    # Create all files
    files = make_files_structure(files_structure)

    # Create FileGroups for each file (simulating what refresh does)
    file_groups = []
    for file_path in files:
        path = pathlib.Path(file_path)
        if path.suffix == '.html':
            fg = FileGroup.from_paths(test_session, path)
            file_groups.append(fg)

    test_session.commit()

    # Verify we have the expected number of FileGroups needing deep indexing
    # Two-phase: indexed=True (surface), deep_indexed=False (needs modeler)
    needs_deep_count = test_session.query(FileGroup).filter(
        FileGroup.indexed == True,
        FileGroup.deep_indexed != True,
        FileGroup.mimetype == 'text/html'
    ).count()
    assert needs_deep_count == num_archives, f"Expected {num_archives} files needing deep indexing, got {needs_deep_count}"

    # Run the archive_modeler
    await archive_modeler()

    # Count how many Archives were created
    archive_count = test_session.query(Archive).count()

    # THE BUG: Only 20 archives created instead of 25
    # After fixing, all 25 should be created
    assert archive_count == num_archives, \
        f"archive_modeler should process ALL {num_archives} files, but only processed {archive_count}. " \
        f"This is the enumerate off-by-one bug!"

    # Also verify all FileGroups are now deep indexed
    still_needs_deep = test_session.query(FileGroup).filter(
        FileGroup.indexed == True,
        FileGroup.deep_indexed != True,
        FileGroup.mimetype == 'text/html'
    ).count()
    assert still_needs_deep == 0, \
        f"All HTML FileGroups should be deep indexed, but {still_needs_deep} remain"
