"""Test for collection_id bug when modeling archives from discovered files.

This test reproduces the bug where Archives created by model_archive()
don't have collection_id set, causing a NOT NULL constraint violation.

The bug happens because:
1. The archive_factory sets collection_id explicitly (masking the bug)
2. But model_archive() (used in production) doesn't set collection_id
3. This causes NULL constraint violations when indexing real files
"""
import pathlib

import pytest

from modules.archive import model_archive
from modules.archive.lib import archive_strftime
from wrolpi.collections import Collection


@pytest.mark.asyncio
async def test_model_archive_sets_collection_id(async_client, test_session, test_directory, make_files_structure):
    """
    Test that model_archive() creates Archives with collection_id set.

    This test uses model_archive() (the production code path) instead of
    archive_factory, so it will detect the collection_id bug.
    """
    import datetime
    import pytz

    # Create archive files with a URL in the singlefile
    domain = 'example.com'
    url = f'https://{domain}/test-page'
    archive_dir = test_directory / 'archives' / domain
    archive_dir.mkdir(parents=True)

    timestamp = archive_strftime(datetime.datetime(2000, 1, 1, 0, 0, 0).astimezone(pytz.UTC))
    title = 'Test Page'

    # Create a minimal singlefile with URL embedded (note trailing space after SingleFile)
    singlefile_content = f'''<!DOCTYPE html> <html lang="en"><!--
 Page saved with SingleFile 
 url: {url}
 saved date: Mon May 16 2022 23:51:35 GMT+0000 (Coordinated Universal Time)
--><head><meta charset="utf-8">
<meta name="generator" content="SingleFile">
<title>{title}</title>
</head>
<body>
<h1>{title}</h1>
<p>Test content</p>
</body>
</html>'''

    files = make_files_structure({
        str(archive_dir / f'{timestamp}_{title}.html'): singlefile_content.strip(),
        str(archive_dir / f'{timestamp}_{title}.readability.json'): '{"title": "' + title + '"}',
    })

    from wrolpi.files.models import FileGroup

    # Create FileGroup from the files (simulating what refresh does)
    file_paths = [pathlib.Path(f) for f in files]
    file_group = FileGroup.from_paths(test_session, *file_paths)

    # Model the archive using the production code path
    # This should create an Archive with collection_id set
    archive = model_archive(test_session, file_group)

    # The bug: collection_id is None, causing NOT NULL constraint violation
    assert archive is not None, "Archive should be created"
    assert archive.collection_id is not None, \
        "Archive.collection_id should be set (this is the bug!)"

    # Verify the collection was created
    collection = test_session.query(Collection).filter_by(
        name=domain,
        kind='domain'
    ).one_or_none()

    assert collection is not None, "Domain collection should be created"
    assert archive.collection_id == collection.id, \
        "Archive should be linked to the domain collection"


@pytest.mark.asyncio
async def test_model_archive_extracts_url_from_singlefile(async_client, test_session, test_directory,
                                                          make_files_structure):
    """
    Test that model_archive() can extract URL from singlefile when file_group.url is None.

    This is the second part of the fix - if the URL isn't in the file_group yet,
    we need to extract it from the singlefile content.
    """
    import datetime
    import pytz

    # Create archive files
    domain = 'test.org'
    url = f'https://{domain}/article'
    archive_dir = test_directory / 'archives' / domain
    archive_dir.mkdir(parents=True)

    timestamp = archive_strftime(datetime.datetime(2000, 1, 1, 0, 0, 0).astimezone(pytz.UTC))

    # Create singlefile with URL in saved-from comment
    singlefile_content = f'''<!DOCTYPE html> <html lang="en"><!--
 Page saved with SingleFile 
 url: {url}
 saved date: Mon May 16 2022 23:51:35 GMT+0000 (Coordinated Universal Time)
--><head><meta charset="utf-8">
<meta name="generator" content="SingleFile">
<title>Test Article</title>
</head>
<body><p>Content</p></body>
</html>'''

    files = make_files_structure({
        str(archive_dir / f'{timestamp}_Test.html'): singlefile_content.strip(),
    })

    from wrolpi.files.models import FileGroup

    # Create FileGroup from the files (simulating what refresh does)
    file_paths = [pathlib.Path(f) for f in files]
    file_group = FileGroup.from_paths(test_session, *file_paths)

    # Model the archive - it should extract the URL from the singlefile
    archive = model_archive(test_session, file_group)

    assert archive is not None
    assert archive.file_group.url == url, \
        "URL should be extracted from singlefile content"
    assert archive.collection_id is not None, \
        "collection_id should be set after URL extraction"

    # Verify collection was created with correct domain
    collection = test_session.query(Collection).get(archive.collection_id)
    assert collection.name == domain
    assert collection.kind == 'domain'
