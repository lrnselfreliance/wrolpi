"""
Tests for domain config import scenarios, specifically around directory detection
when archives are organized in year subdirectories.

These tests expose the bug where detect_domain_directory() returns the year directory
(e.g., archive/x.com/2026) instead of the domain directory (archive/x.com) when archives
are organized with year subdirectories.

These tests use the REAL import flow:
1. Create archive files on disk
2. Run refresh_files() to trigger file indexing and archive modeling
3. Archive modeling calls get_or_create_domain_collection() → detect_domain_directory()
4. Verify the detected directory is correct
"""

import pytest

from modules.archive.lib import import_domains_config
from wrolpi import tags
from wrolpi.collections import Collection


# Valid singlefile content with the required header
def make_singlefile_content(url: str, title: str = 'Test Article') -> str:
    return f'''<html><!--
 Page saved with SingleFile
 url: {url}
 saved date: Thu May 12 2022 00:38:02 GMT+0000 (Coordinated Universal Time)
--><head><meta charset="utf-8">
<title>{title}</title>
</head>
<body>
{title} body contents
</body>
</html>
'''


class TestNonTaggedDomainDirectoryDetection:
    """Tests that non-tagged domain directories are correctly detected."""

    @pytest.mark.asyncio
    async def test_detect_domain_directory_non_tagged(
            self, async_client, test_session, archive_directory):
        """
        Non-tagged domain directories should be detected when they exist.

        If archive/example.com exists, it should be returned by detect_domain_directory()
        for a collection with no tag.
        """
        from modules.archive.lib import detect_domain_directory

        # Create a domain collection WITHOUT a tag
        collection = Collection(name='example.com', kind='domain', directory=None)
        test_session.add(collection)
        test_session.flush()

        # Verify no tag
        assert collection.tag is None, 'Collection should not have a tag'

        # Create the expected directory on filesystem
        # For non-tagged domains, format_destination(None) should return archive/example.com
        expected_dir = archive_directory / 'example.com'
        expected_dir.mkdir(parents=True, exist_ok=True)

        # detect_domain_directory should find this directory
        detected = detect_domain_directory(collection)
        assert detected is not None, \
            f'detect_domain_directory should find directory for non-tagged domain. Expected: archive/example.com'
        assert 'example.com' in str(detected), f'Detected directory should contain domain name, got {detected}'

    @pytest.mark.asyncio
    async def test_detect_domain_directory_non_tagged_directory_missing(
            self, async_client, test_session, archive_directory):
        """
        When directory doesn't exist, detect_domain_directory should return None.
        """
        from modules.archive.lib import detect_domain_directory

        # Create a domain collection WITHOUT a tag
        collection = Collection(name='missing.com', kind='domain', directory=None)
        test_session.add(collection)
        test_session.flush()

        # DO NOT create the directory - it should not exist

        # detect_domain_directory should return None
        detected = detect_domain_directory(collection)
        assert detected is None, \
            'detect_domain_directory should return None when directory does not exist'

    @pytest.mark.asyncio
    async def test_archive_modeling_creates_non_tagged_collection_with_directory(
            self, async_client, test_session, archive_directory, make_files_structure, refresh_files):
        """
        When archives are created for a non-tagged domain, the collection
        should be created with the correct directory auto-detected.

        This is the full integration test: files on disk -> modeling -> collection with directory.
        """
        # Create archive files in non-tagged domain directory (no tag subdirectory)
        domain_dir = archive_directory / 'simple.com'
        domain_dir.mkdir(parents=True, exist_ok=True)

        make_files_structure({
            str(domain_dir / '2026-01-01-00-00-01_Simple Article.html'):
                make_singlefile_content('https://simple.com/article', 'Simple Article'),
            str(domain_dir / '2026-01-01-00-00-01_Simple Article.readability.json'):
                '{"url": "https://simple.com/article", "title": "Simple Article"}',
        })

        await refresh_files()

        # Verify domain collection was created WITHOUT a tag
        collection = test_session.query(Collection).filter_by(name='simple.com', kind='domain').one_or_none()
        assert collection is not None, 'Domain collection should have been created'
        assert collection.tag is None, 'Collection should NOT have a tag'

        # Directory should have been auto-detected
        assert collection.directory is not None, 'Directory should have been auto-detected'
        dir_str = str(collection.directory)
        assert 'archive/simple.com' in dir_str, f'Directory should be archive/simple.com, got {dir_str}'


class TestArchiveModelingWithYearSubdirs:
    """Tests using real archive modeling flow with year subdirectories."""

    @pytest.mark.asyncio
    async def test_archive_modeling_year_subdirectory_detection(
            self, async_client, test_session, archive_directory, make_files_structure, refresh_files):
        """
        Bug test: When archives are in year subdirectories, the domain collection
        should have directory archive/x.com, not archive/x.com/2026.

        Uses real refresh flow to trigger archive modeling.
        """
        # Create archive files in year subdirectory
        year_dir = archive_directory / 'x.com' / '2026'
        year_dir.mkdir(parents=True, exist_ok=True)

        make_files_structure({
            str(year_dir / '2026-01-01-00-00-01_Article 1.html'):
                make_singlefile_content('https://x.com/article1', 'Article 1'),
            str(year_dir / '2026-01-01-00-00-01_Article 1.readability.json'):
                '{"url": "https://x.com/article1", "title": "Article 1"}',
            str(year_dir / '2026-01-01-00-00-02_Article 2.html'):
                make_singlefile_content('https://x.com/article2', 'Article 2'),
            str(year_dir / '2026-01-01-00-00-02_Article 2.readability.json'):
                '{"url": "https://x.com/article2", "title": "Article 2"}',
        })

        # Run file refresh - this triggers archive modeling which calls
        # get_or_create_domain_collection() → detect_domain_directory()
        await refresh_files()

        # Verify domain collection was created
        collection = test_session.query(Collection).filter_by(name='x.com', kind='domain').one_or_none()
        assert collection is not None, 'Domain collection should have been created'

        # BUG: Currently detects archive/x.com/2026 instead of archive/x.com
        # The directory should be the domain directory, not the year subdirectory
        assert collection.directory is not None, 'Directory should have been auto-detected'
        dir_str = str(collection.directory)
        assert 'archive/x.com' in dir_str, f'Directory should contain archive/x.com, got {dir_str}'
        assert '2026' not in dir_str, f'Directory should NOT contain year subdirectory, got {dir_str}'

    @pytest.mark.asyncio
    async def test_archive_modeling_multiple_year_subdirectories(
            self, async_client, test_session, archive_directory, make_files_structure, refresh_files):
        """
        When archives span multiple years, the domain collection directory
        should be the common parent (archive/example.org), not either year.
        """
        # Create archives in different year subdirectories
        year_2025 = archive_directory / 'example.org' / '2025'
        year_2026 = archive_directory / 'example.org' / '2026'
        year_2025.mkdir(parents=True, exist_ok=True)
        year_2026.mkdir(parents=True, exist_ok=True)

        make_files_structure({
            str(year_2025 / '2025-06-01-00-00-01_Old Article.html'):
                make_singlefile_content('https://example.org/old', 'Old Article'),
            str(year_2025 / '2025-06-01-00-00-01_Old Article.readability.json'):
                '{"url": "https://example.org/old", "title": "Old Article"}',
            str(year_2026 / '2026-01-01-00-00-01_New Article.html'):
                make_singlefile_content('https://example.org/new', 'New Article'),
            str(year_2026 / '2026-01-01-00-00-01_New Article.readability.json'):
                '{"url": "https://example.org/new", "title": "New Article"}',
        })

        await refresh_files()

        collection = test_session.query(Collection).filter_by(name='example.org', kind='domain').one_or_none()
        assert collection is not None
        assert collection.directory is not None

        dir_str = str(collection.directory)
        assert 'archive/example.org' in dir_str
        # Should not contain either year
        assert '2025' not in dir_str, f'Directory should not contain 2025, got {dir_str}'
        assert '2026' not in dir_str, f'Directory should not contain 2026, got {dir_str}'

    @pytest.mark.asyncio
    async def test_archive_modeling_tagged_domain_with_year_subdirs(
            self, async_client, test_session, test_directory, archive_directory,
            make_files_structure, test_tags_config, refresh_files):
        """
        For tagged domains, the directory should be archive/tag/domain, not archive/tag/domain/year.

        Tags are associated via config import, not auto-detected from paths.
        """
        from wrolpi import tags
        from modules.archive.lib import import_domains_config

        # Create config directory
        config_dir = test_directory / 'config'
        config_dir.mkdir(exist_ok=True)

        # Create tags config with the 'news' tag
        test_tags_config.write_text('''
version: 0
tags:
  news:
    color: '#FF0000'
''')

        # Create domains config with tag association
        domains_config_path = config_dir / 'domains.yaml'
        domains_config_path.write_text('''
version: 0
collections:
  - name: x.com
    kind: domain
    tag_name: news
''')

        # Import configs to set up tag association
        tags.import_tags_config()
        import_domains_config()

        # Create archives in tagged domain with year subdirectory
        tagged_year_dir = archive_directory / 'news' / 'x.com' / '2026'
        tagged_year_dir.mkdir(parents=True, exist_ok=True)

        make_files_structure({
            str(tagged_year_dir / '2026-01-01-00-00-01_Tagged Article.html'):
                make_singlefile_content('https://x.com/tagged', 'Tagged Article'),
            str(tagged_year_dir / '2026-01-01-00-00-01_Tagged Article.readability.json'):
                '{"url": "https://x.com/tagged", "title": "Tagged Article"}',
        })

        await refresh_files()

        # The collection should exist with tag association from config
        collection = test_session.query(Collection).filter_by(name='x.com', kind='domain').one_or_none()
        assert collection is not None
        assert collection.tag is not None
        assert collection.tag.name == 'news'

        # Directory should be archive/news/x.com, not archive/news/x.com/2026
        assert collection.directory is not None
        dir_str = str(collection.directory)
        assert '2026' not in dir_str, f'Directory should not contain year, got {dir_str}'


class TestConfigImportThenModeling:
    """Tests for config import followed by archive modeling."""

    @pytest.mark.asyncio
    async def test_config_import_then_archive_modeling(
            self, async_client, test_session, test_directory, archive_directory,
            make_files_structure, test_tags_config, refresh_files):
        """
        Test full flow:
        1. Import domains config (creates unrestricted collection)
        2. Create archive files on disk
        3. Run refresh (triggers modeling and directory detection)
        4. Verify directory is correctly detected
        """
        # Create tags config
        config_dir = test_directory / 'config'
        config_dir.mkdir(exist_ok=True)
        test_tags_config.write_text('''
version: 0
tags:
  news:
    color: '#FF0000'
''')

        # Create domains config - collection without directory initially
        domains_config_path = config_dir / 'domains.yaml'
        domains_config_path.write_text('''
version: 0
collections:
  - name: test.com
    kind: domain
    tag_name: news
''')

        # Import configs
        tags.import_tags_config()
        import_domains_config()

        # Verify collection was created WITHOUT directory
        collection = test_session.query(Collection).filter_by(name='test.com', kind='domain').one()
        assert collection.tag is not None
        assert collection.tag.name == 'news'
        # Collection should be unrestricted (no directory yet)
        initial_directory = collection.directory

        # Now create archive files in year subdirectory
        year_dir = archive_directory / 'news' / 'test.com' / '2026'
        year_dir.mkdir(parents=True, exist_ok=True)

        make_files_structure({
            str(year_dir / '2026-01-01-00-00-01_Test Article.html'):
                make_singlefile_content('https://test.com/article', 'Test Article'),
            str(year_dir / '2026-01-01-00-00-01_Test Article.readability.json'):
                '{"url": "https://test.com/article", "title": "Test Article"}',
        })

        # Run refresh to trigger archive modeling
        await refresh_files()

        # Refresh the collection from DB
        test_session.expire(collection)

        # Directory should now be detected - but NOT include the year
        if collection.directory is not None:
            dir_str = str(collection.directory)
            assert '2026' not in dir_str, f'Directory should not contain year, got {dir_str}'

    @pytest.mark.asyncio
    async def test_full_startup_import_sequence(
            self, async_client, test_session, test_directory, archive_directory, test_tags_config):
        """
        Replicate exact main.py import order to verify tag associations exist
        before domain directory detection runs.
        """
        from wrolpi.tags import Tag

        # Create tag
        news_tag = Tag(name='news')
        test_session.add(news_tag)
        test_session.commit()

        # Create tags config
        config_dir = test_directory / 'config'
        config_dir.mkdir(exist_ok=True)
        test_tags_config.write_text('''
version: 0
tags:
  news:
    color: '#0000FF'
''')

        # Create domains config
        domains_config_path = config_dir / 'domains.yaml'
        domains_config_path.write_text('''
version: 0
collections:
  - name: startup-test.com
    kind: domain
    tag_name: news
''')

        # Import in exact main.py order
        tags.import_tags_config()
        import_domains_config()

        # Verify tag association was created
        collection = test_session.query(Collection).filter_by(name='startup-test.com', kind='domain').one()
        assert collection.tag is not None
        assert collection.tag.name == 'news'


class TestArchiveFileFormatInteraction:
    """Tests for interaction between archive_file_format config and directory detection."""

    @pytest.mark.asyncio
    async def test_archive_file_format_with_year_subdirectory(
            self, async_client, test_session, test_directory, archive_directory,
            make_files_structure, refresh_files, fake_now):
        """
        Test that directory detection works correctly when archive_file_format
        includes year subdirectories.

        This tests the interaction between:
        1. archive_file_format config (e.g., %(download_year)s/%(download_datetime)s_%(title)s.%(ext)s)
        2. detect_domain_directory() which should return archive/example.com, NOT archive/example.com/2026

        Uses get_new_archive_files() to create files exactly as the real download flow does.
        """
        from datetime import datetime
        from modules.archive.lib import get_new_archive_files, get_archive_downloader_config

        # Set the fake time so we know what year subdirectory will be created
        fake_now(datetime(2026, 6, 15))

        # Configure archive_file_format to use year subdirectories
        config = get_archive_downloader_config()
        original_format = config._config['file_name_format']
        config._config['file_name_format'] = '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'

        try:
            # Use get_new_archive_files to create file paths exactly as real download does
            archive_files = get_new_archive_files('https://fileformat-test.com/article', 'Test Article')

            # Verify the files are in a year subdirectory
            assert '2026' in str(archive_files.singlefile), f'File should be in year subdir: {archive_files.singlefile}'

            # Create the directory structure and write the files
            archive_files.singlefile.parent.mkdir(parents=True, exist_ok=True)
            archive_files.singlefile.write_text(
                make_singlefile_content('https://fileformat-test.com/article', 'Test Article'))
            archive_files.readability_json.write_text(
                '{"url": "https://fileformat-test.com/article", "title": "Test Article"}')

            # Run refresh to trigger archive modeling
            await refresh_files()

            # Verify domain collection was created
            collection = test_session.query(Collection).filter_by(
                name='fileformat-test.com', kind='domain').one_or_none()
            assert collection is not None, 'Domain collection should have been created'

            # BUG: Currently detects archive/fileformat-test.com/2026 instead of archive/fileformat-test.com
            assert collection.directory is not None, 'Directory should have been auto-detected'
            dir_str = str(collection.directory)
            assert 'archive/fileformat-test.com' in dir_str, f'Directory should contain domain, got {dir_str}'
            assert '2026' not in dir_str, f'Directory should NOT contain year from file format, got {dir_str}'

        finally:
            # Restore original format
            config._config['file_name_format'] = original_format

    @pytest.mark.asyncio
    async def test_archive_file_format_multiple_downloads_same_year(
            self, async_client, test_session, test_directory, archive_directory,
            make_files_structure, refresh_files, fake_now):
        """
        Test directory detection when multiple archives are downloaded in the same year
        using archive_file_format with year subdirectories.
        """
        from datetime import datetime
        from modules.archive.lib import get_new_archive_files, get_archive_downloader_config

        fake_now(datetime(2026, 3, 10))

        config = get_archive_downloader_config()
        original_format = config._config['file_name_format']
        config._config['file_name_format'] = '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'

        try:
            # Create multiple archives in the same year
            for i, title in enumerate(['Article One', 'Article Two', 'Article Three'], 1):
                fake_now(datetime(2026, 3, 10, 0, 0, i))  # Different times, same year
                archive_files = get_new_archive_files(f'https://multi-test.com/article{i}', title)
                archive_files.singlefile.parent.mkdir(parents=True, exist_ok=True)
                archive_files.singlefile.write_text(
                    make_singlefile_content(f'https://multi-test.com/article{i}', title))
                archive_files.readability_json.write_text(
                    f'{{"url": "https://multi-test.com/article{i}", "title": "{title}"}}')

            await refresh_files()

            collection = test_session.query(Collection).filter_by(
                name='multi-test.com', kind='domain').one_or_none()
            assert collection is not None

            # BUG: All archives in 2026/, so common ancestor is archive/multi-test.com/2026
            # Should be archive/multi-test.com
            assert collection.directory is not None
            dir_str = str(collection.directory)
            assert 'archive/multi-test.com' in dir_str
            assert '2026' not in dir_str, f'Directory should NOT contain year, got {dir_str}'

        finally:
            config._config['file_name_format'] = original_format
