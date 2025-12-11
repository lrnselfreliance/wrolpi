import pathlib
from datetime import datetime

import pytest

from modules.archive import Archive
from wrolpi.common import get_wrolpi_config
from wrolpi.errors import UnknownArchive


def test_archive_get_by_id(test_session, archive_factory):
    """Archive.get_by_id should accept session as first argument, id as second."""
    archive = archive_factory()
    test_session.commit()

    # Session must be first argument (session-first pattern)
    found = Archive.get_by_id(test_session, archive.id)
    assert found is not None
    assert found.id == archive.id

    # Non-existent ID should return None
    not_found = Archive.get_by_id(test_session, 99999)
    assert not_found is None


def test_archive_find_by_id(test_session, archive_factory):
    """Archive.find_by_id should accept session as first argument, id as second."""
    archive = archive_factory()
    test_session.commit()

    # Session must be first argument (session-first pattern)
    found = Archive.find_by_id(test_session, archive.id)
    assert found is not None
    assert found.id == archive.id

    # Non-existent ID should raise UnknownArchive
    with pytest.raises(UnknownArchive):
        Archive.find_by_id(test_session, 99999)


@pytest.mark.asyncio
async def test_archive_download_destination(async_client, test_session, test_directory, archive_factory, fake_now):
    fake_now(datetime(2000, 1, 2))

    wrolpi_config = get_wrolpi_config()

    archive = archive_factory(domain='wrolpi.org')
    test_session.commit()

    # Test the default download directory.
    assert str(archive.download_directory) == str(test_directory / 'archive/wrolpi.org')

    # Year of download is supported.
    wrolpi_config.archive_destination = 'archives/%(domain)s/%(year)s'
    assert str(archive.download_directory) == str(test_directory / 'archives/wrolpi.org/2000')

    # More download date is supported.
    wrolpi_config.archive_destination = 'archive/%(domain)s/%(year)s/%(month)s/%(day)s'
    assert str(archive.download_directory) == str(test_directory / 'archive/wrolpi.org/2000/1/2')


@pytest.mark.asyncio
async def test_set_screenshot(async_client, test_session, archive_factory, image_bytes_factory):
    """Test Archive.set_screenshot() method with various scenarios."""

    # ========== Test 1: Successfully set screenshot on archive without one ==========
    archive = archive_factory('example.com', 'https://example.com/test', 'Test Archive', screenshot=False)
    test_session.commit()

    # Verify no screenshot initially
    assert archive.screenshot_path is None

    # Create a screenshot file
    screenshot_path = archive.singlefile_path.parent / 'test_screenshot.png'
    screenshot_path.write_bytes(image_bytes_factory())

    # Set the screenshot
    archive.set_screenshot(screenshot_path)

    # Verify data was set before commit
    assert archive.file_group.data['screenshot_path'] == str(screenshot_path), \
        f"Data not set correctly before commit: {archive.file_group.data.get('screenshot_path')}"

    test_session.commit()

    # Refresh the archive to get latest data from DB
    test_session.expire_all()
    archive = test_session.query(Archive).filter_by(id=archive.id).one()

    # Verify screenshot was set
    assert archive.screenshot_path == screenshot_path
    assert archive.screenshot_file is not None
    # Verify FileGroup.data was persisted to DB (FancyJSON converts strings back to Path objects)
    assert 'screenshot_path' in archive.file_group.data
    assert str(archive.file_group.data['screenshot_path']) == str(screenshot_path)

    # Verify file is tracked in FileGroup.files
    screenshot_files = archive.file_group.my_files('image/')
    assert len(screenshot_files) > 0
    assert screenshot_files[0]['path'] == screenshot_path

    # ========== Test 2: Error when trying to set screenshot on archive that already has one ==========
    original_screenshot = archive.screenshot_path
    assert original_screenshot is not None

    # Try to set another screenshot
    new_screenshot_path = archive.singlefile_path.parent / 'another_screenshot.png'
    new_screenshot_path.write_bytes(b'fake image data')

    # Should raise ValueError
    with pytest.raises(ValueError, match='already has a screenshot'):
        archive.set_screenshot(new_screenshot_path)

    # Verify original screenshot is unchanged
    assert archive.screenshot_path == original_screenshot

    # ========== Test 3: Error when trying to set non-existent screenshot file ==========
    archive_no_screenshot = archive_factory('example.com', 'https://example.com/test2', 'Test Archive 2',
                                            screenshot=False)
    test_session.commit()

    # Try to set a screenshot that doesn't exist
    nonexistent_path = pathlib.Path('/tmp/does_not_exist.png')

    # Should raise ValueError
    with pytest.raises(ValueError, match='does not exist'):
        archive_no_screenshot.set_screenshot(nonexistent_path)

    # Verify no screenshot was set
    assert archive_no_screenshot.screenshot_path is None
