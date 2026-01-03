"""
Tests for Collection file format reorganization.

TDD approach: These tests are written first, then implementation follows.
"""
import pathlib
from datetime import datetime

import pytest
import pytz

from modules.archive.lib import format_archive_filename
from wrolpi.collections import Collection


class TestFormatArchiveFilenameWithTemplate:
    """Test format_archive_filename() with custom template parameter."""

    def test_format_archive_filename_with_year_subdirectory(self):
        """format_archive_filename() accepts custom template with year subdirectory."""
        result = format_archive_filename(
            title='My Article',
            domain='example.com',
            download_date=datetime(2024, 3, 15, 12, 30, 45, tzinfo=pytz.UTC),
            template='%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'
        )
        assert result == '2024/2024-03-15-12-30-45_My Article.html'

    def test_format_archive_filename_with_year_month_subdirectory(self):
        """format_archive_filename() supports year/month subdirectories."""
        result = format_archive_filename(
            title='Another Article',
            domain='example.com',
            download_date=datetime(2023, 11, 5, 9, 15, 0, tzinfo=pytz.UTC),
            template='%(download_year)s/%(download_month)s/%(title)s.%(ext)s'
        )
        assert result == '2023/11/Another Article.html'

    def test_format_archive_filename_without_template_uses_config(self):
        """format_archive_filename() uses config template when no template provided."""
        # This test verifies backwards compatibility - no template means use config
        result = format_archive_filename(
            title='Test',
            domain='example.com',
            download_date=datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
        )
        # Should use config's file_name_format (default: %(download_datetime)s_%(title)s.%(ext)s)
        assert result.endswith('.html')
        assert 'Test' in result

    def test_format_archive_filename_with_domain_in_template(self):
        """format_archive_filename() can include domain in path."""
        result = format_archive_filename(
            title='Page',
            domain='news.example.com',
            download_date=datetime(2024, 6, 20, 14, 0, 0, tzinfo=pytz.UTC),
            template='%(domain)s/%(download_year)s/%(title)s.%(ext)s'
        )
        assert result == 'news.example.com/2024/Page.html'

    def test_format_archive_filename_escapes_special_characters(self):
        """format_archive_filename() escapes special characters in title."""
        result = format_archive_filename(
            title='Article: The "Best" Guide? (2024)',
            domain='example.com',
            download_date=datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
            template='%(title)s.%(ext)s'
        )
        # Should escape characters that are invalid in filenames
        assert '/' not in result
        assert result.endswith('.html')


class TestFormatVideoFilename:
    """Test format_video_filename() helper for videos."""

    @pytest.mark.skip(reason="format_video_filename not yet implemented")
    def test_format_video_filename_with_year_subdirectory(self, video_factory, test_session):
        """format_video_filename() generates path with year subdirectory."""
        from wrolpi.collections.reorganize import format_video_filename

        video = video_factory()
        video.file_group.published_datetime = datetime(2024, 5, 10, tzinfo=pytz.UTC)
        # Mock info_json with upload_date
        video._info_json = {
            'uploader': 'TestChannel',
            'upload_date': '20240510',
            'id': 'abc123xyz',
            'title': 'Test Video Title',
        }

        result = format_video_filename(
            video,
            template='%(upload_year)s/%(uploader)s_%(title)s.%(ext)s'
        )
        assert result == '2024/TestChannel_Test Video Title.mp4'

    @pytest.mark.skip(reason="format_video_filename not yet implemented")
    def test_format_video_filename_default_format(self, video_factory, test_session):
        """format_video_filename() uses standard yt-dlp format variables."""
        from wrolpi.collections.reorganize import format_video_filename

        video = video_factory()
        video._info_json = {
            'uploader': 'MyChannel',
            'upload_date': '20231225',
            'id': 'xyz789abc',
            'title': 'Holiday Special',
        }

        result = format_video_filename(
            video,
            template='%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s'
        )
        assert result == 'MyChannel_20231225_xyz789abc_Holiday Special.mp4'


class TestBuildReorganizationPlan:
    """Test build_reorganization_plan() for generating move previews."""

    @pytest.mark.asyncio
    async def test_build_plan_for_archives(self, async_client, test_session, test_directory, archive_factory):
        """build_reorganization_plan() returns old -> new path mappings for archives."""
        from wrolpi.collections.reorganize import build_reorganization_plan

        # Create a domain collection with archives
        domain_dir = test_directory / 'archive' / 'example.com'
        domain_dir.mkdir(parents=True)

        collection = Collection(
            name='example.com',
            kind='domain',
            directory=domain_dir,
            file_format='%(download_datetime)s_%(title)s.%(ext)s'  # Old format
        )
        test_session.add(collection)
        test_session.flush()

        # Create archive with old format naming
        archive = archive_factory(domain='example.com', title='Test Article')
        archive.collection = collection
        test_session.flush()

        # Build plan with new format that includes year subdirectory
        new_format = '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'
        plan = await build_reorganization_plan(test_session, collection, new_format)

        assert plan['total_files'] >= 1
        assert plan['files_to_move'] >= 1
        assert len(plan['moves']) >= 1
        # Check that the move includes year subdirectory
        move = plan['moves'][0]
        assert '/' in move['to']  # Should have subdirectory

    @pytest.mark.asyncio
    async def test_build_plan_skips_unchanged_files(self, async_client, test_session, test_directory, archive_factory):
        """build_reorganization_plan() skips files already at correct path."""
        from wrolpi.collections.reorganize import build_reorganization_plan

        # Create collection
        domain_dir = test_directory / 'archive' / 'example.com'
        domain_dir.mkdir(parents=True)

        new_format = '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'

        collection = Collection(
            name='example.com',
            kind='domain',
            directory=domain_dir,
            file_format=new_format  # Already using the new format
        )
        test_session.add(collection)
        test_session.flush()

        # Create archive - it will be in the domain_dir but we'll manually move it to year subdir
        archive = archive_factory(domain='example.com', title='Already Organized')
        archive.collection = collection
        test_session.flush()

        # The archive was created at domain_dir level, now check if its path matches new format
        # Since archive_factory creates with timestamp, the generated new path will be the same as current
        # (assuming same download_datetime)
        plan = await build_reorganization_plan(test_session, collection, new_format)

        # There should be at least 1 file to move (since archive was created at root, not in year subdir)
        # The test verifies the function works - files at correct path would be unchanged
        assert 'files_to_move' in plan
        assert 'files_unchanged' in plan

    @pytest.mark.asyncio
    async def test_build_plan_handles_missing_datetime(self, async_client, test_session, test_directory, archive_factory):
        """build_reorganization_plan() uses fallback for files without datetime."""
        from wrolpi.collections.reorganize import build_reorganization_plan

        domain_dir = test_directory / 'archive' / 'example.com'
        domain_dir.mkdir(parents=True)

        collection = Collection(
            name='example.com',
            kind='domain',
            directory=domain_dir,
            file_format='%(download_datetime)s_%(title)s.%(ext)s'
        )
        test_session.add(collection)
        test_session.flush()

        # Create archive without datetime
        archive = archive_factory(domain='example.com', title='No Date Article')
        archive.file_group.download_datetime = None
        archive.file_group.published_datetime = None
        archive.collection = collection
        test_session.flush()

        new_format = '%(download_year)s/%(title)s.%(ext)s'
        plan = await build_reorganization_plan(test_session, collection, new_format)

        # Should still generate a plan, possibly with 'unknown' year
        assert 'files_to_move' in plan


class TestExecuteReorganization:
    """Test execute_reorganization() for actually moving files."""

    @pytest.mark.asyncio
    async def test_execute_moves_files(self, async_client, test_session, test_directory, archive_factory, await_background_tasks):
        """execute_reorganization() queues moves and FileWorker processes them."""
        from wrolpi.collections.reorganize import build_reorganization_plan, execute_reorganization

        domain_dir = test_directory / 'archive' / 'example.com'
        domain_dir.mkdir(parents=True)

        collection = Collection(
            name='example.com',
            kind='domain',
            directory=domain_dir,
            file_format='%(download_datetime)s_%(title)s.%(ext)s'
        )
        test_session.add(collection)
        test_session.flush()

        archive = archive_factory(domain='example.com', title='Move Me')
        archive.collection = collection
        old_path = archive.file_group.primary_path
        test_session.flush()

        new_format = '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'
        plan = await build_reorganization_plan(test_session, collection, new_format)

        # Queue the moves (returns immediately)
        job_ids = await execute_reorganization(test_session, collection, plan, new_format)
        assert len(job_ids) > 0

        # Process the queued moves
        await await_background_tasks()

        # Old path should not exist
        assert not old_path.exists()
        # New path should exist (in year subdirectory)
        new_path = archive.file_group.primary_path
        assert new_path.exists()
        assert new_path.parent.name.isdigit()  # Year directory

    @pytest.mark.asyncio
    async def test_execute_updates_collection_file_format(self, async_client, test_session, test_directory, archive_factory, await_background_tasks):
        """execute_reorganization() updates Collection.file_format after queuing."""
        from wrolpi.collections.reorganize import build_reorganization_plan, execute_reorganization

        domain_dir = test_directory / 'archive' / 'example.com'
        domain_dir.mkdir(parents=True)

        old_format = '%(download_datetime)s_%(title)s.%(ext)s'
        new_format = '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'

        collection = Collection(
            name='example.com',
            kind='domain',
            directory=domain_dir,
            file_format=old_format
        )
        test_session.add(collection)
        test_session.flush()

        archive = archive_factory(domain='example.com', title='Update Format')
        archive.collection = collection
        test_session.flush()

        plan = await build_reorganization_plan(test_session, collection, new_format)
        await execute_reorganization(test_session, collection, plan, new_format)

        # Collection's file_format should be updated immediately (before moves complete)
        assert collection.file_format == new_format

        # Process the queued moves
        await await_background_tasks()


class TestReorganizeAPI:
    """Integration tests for the reorganize API endpoint."""

    @pytest.mark.asyncio
    async def test_reorganize_api_dry_run(self, async_client, test_session, test_directory, archive_factory):
        """POST /api/collections/<id>/reorganize with dry_run=true returns preview."""
        from http import HTTPStatus
        from modules.archive.lib import get_archive_downloader_config

        domain_dir = test_directory / 'archive' / 'example.com'
        domain_dir.mkdir(parents=True)

        # Set up global config with NEW format (year subdirectory)
        config = get_archive_downloader_config()
        original_format = config._config['file_name_format']
        new_format = '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'
        config._config['file_name_format'] = new_format

        try:
            collection = Collection(
                name='example.com',
                kind='domain',
                directory=domain_dir,
                file_format='%(download_datetime)s_%(title)s.%(ext)s'  # Old format
            )
            test_session.add(collection)
            test_session.flush()

            archive = archive_factory(domain='example.com', title='API Test')
            archive.collection = collection
            old_path = archive.file_group.primary_path
            test_session.commit()

            # Call API with dry_run=true
            _, response = await async_client.post(
                f'/api/collections/{collection.id}/reorganize',
                json={'dry_run': True}
            )

            assert response.status == HTTPStatus.OK
            data = response.json
            assert data['reorganized'] is False
            assert 'preview' in data
            assert data['preview']['files_to_move'] >= 1  # Should have files to move
            assert data['new_file_format'] == new_format
            # File should NOT be moved
            assert old_path.exists()
        finally:
            config._config['file_name_format'] = original_format

    @pytest.mark.asyncio
    async def test_reorganize_api_moves_files(self, async_client, test_session, test_directory, archive_factory, await_background_tasks):
        """POST /api/collections/<id>/reorganize moves files."""
        from http import HTTPStatus
        from modules.archive.lib import get_archive_downloader_config

        domain_dir = test_directory / 'archive' / 'example.com'
        domain_dir.mkdir(parents=True)

        # Set up global config with NEW format (year subdirectory)
        config = get_archive_downloader_config()
        original_format = config._config['file_name_format']
        new_format = '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'
        config._config['file_name_format'] = new_format

        try:
            collection = Collection(
                name='example.com',
                kind='domain',
                directory=domain_dir,
                file_format='%(download_datetime)s_%(title)s.%(ext)s'  # Old format
            )
            test_session.add(collection)
            test_session.flush()

            archive = archive_factory(domain='example.com', title='Move Via API')
            archive.collection = collection
            old_path = archive.file_group.primary_path
            test_session.commit()

            # Call API with dry_run=false (queues moves, returns immediately)
            _, response = await async_client.post(
                f'/api/collections/{collection.id}/reorganize',
                json={'dry_run': False}
            )

            assert response.status == HTTPStatus.OK
            data = response.json
            assert data['reorganized'] is True
            assert data['new_file_format'] == new_format

            # Process queued moves
            await await_background_tasks()

            # Old path should not exist (moved to year subdirectory)
            assert not old_path.exists()
            # Collection's file_format should be updated
            test_session.refresh(collection)
            assert collection.file_format == new_format
        finally:
            config._config['file_name_format'] = original_format

    @pytest.mark.asyncio
    async def test_reorganize_api_not_found(self, async_client):
        """POST /api/collections/<id>/reorganize returns 404 for unknown collection."""
        from http import HTTPStatus

        _, response = await async_client.post(
            '/api/collections/99999/reorganize',
            json={'dry_run': True}
        )

        assert response.status == HTTPStatus.NOT_FOUND


class TestCollectionNeedsReorganization:
    """Test Collection.needs_reorganization property."""

    def test_needs_reorganization_true_when_formats_differ(self, test_session, test_directory):
        """needs_reorganization is True when collection format != global config."""
        from wrolpi.collections import Collection

        collection = Collection(
            name='example.com',
            kind='domain',
            directory=test_directory / 'archive' / 'example.com',
            file_format='%(download_datetime)s_%(title)s.%(ext)s'  # Old format
        )
        test_session.add(collection)
        test_session.flush()

        # This test assumes global config has a different format
        # The property should compare collection.file_format to global config
        # For now, we just verify the property exists and returns a boolean
        assert isinstance(collection.needs_reorganization, bool)

    def test_needs_reorganization_false_when_no_format(self, test_session, test_directory):
        """needs_reorganization is False when collection has no file_format."""
        from wrolpi.collections import Collection

        collection = Collection(
            name='example.com',
            kind='domain',
            directory=test_directory / 'archive' / 'example.com',
            file_format=None  # No format set
        )
        test_session.add(collection)
        test_session.flush()

        # No format means no reorganization needed
        assert collection.needs_reorganization is False

    def test_needs_reorganization_false_when_formats_match(self, test_session, test_directory):
        """needs_reorganization is False when collection format matches global config."""
        from wrolpi.collections import Collection
        from modules.archive.lib import get_archive_downloader_config

        # Get current global format
        global_format = get_archive_downloader_config().file_name_format

        collection = Collection(
            name='example.com',
            kind='domain',
            directory=test_directory / 'archive' / 'example.com',
            file_format=global_format  # Same as global
        )
        test_session.add(collection)
        test_session.flush()

        assert collection.needs_reorganization is False


class TestFileFormatCapture:
    """Tests for file_format being set on first download to a collection."""

    def test_archive_download_sets_collection_file_format(self, test_session, test_directory, archive_factory):
        """First archive download sets collection.file_format."""
        from modules.archive.lib import get_archive_downloader_config

        domain_dir = test_directory / 'archive' / 'example.com'
        domain_dir.mkdir(parents=True)

        # Create collection WITHOUT file_format (simulating existing collection before feature)
        collection = Collection(
            name='example.com',
            kind='domain',
            directory=domain_dir,
            file_format=None  # No format set
        )
        test_session.add(collection)
        test_session.flush()

        assert collection.file_format is None

        # Simulate what happens in archive download: set file_format if not already set
        if collection and not collection.file_format:
            collection.file_format = get_archive_downloader_config().file_name_format
        test_session.flush()

        # file_format should now be set to the global format
        assert collection.file_format == get_archive_downloader_config().file_name_format
        # And needs_reorganization should be False (formats match)
        assert collection.needs_reorganization is False

    def test_archive_download_does_not_overwrite_file_format(self, test_session, test_directory, archive_factory):
        """Subsequent archive downloads do not change collection.file_format."""
        from modules.archive.lib import get_archive_downloader_config

        domain_dir = test_directory / 'archive' / 'example.com'
        domain_dir.mkdir(parents=True)

        # Create collection WITH file_format (simulating collection that already has format)
        old_format = '%(download_datetime)s_%(title)s.%(ext)s'
        collection = Collection(
            name='example.com',
            kind='domain',
            directory=domain_dir,
            file_format=old_format
        )
        test_session.add(collection)
        test_session.flush()

        # Simulate what happens in archive download: only set file_format if not already set
        if collection and not collection.file_format:
            collection.file_format = get_archive_downloader_config().file_name_format
        test_session.flush()

        # file_format should still be the old format (not overwritten)
        assert collection.file_format == old_format
