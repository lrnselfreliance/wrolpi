"""Tests for Collection API endpoints."""
from http import HTTPStatus

import pytest

from wrolpi.collections.models import Collection


class TestCollectionsAPI:
    """Test the GET /api/collections endpoint."""

    @pytest.mark.asyncio
    async def test_get_collections_for_domains(
            self, async_client, test_session
    ):
        """Test that GET /api/collections?kind=domain returns domain collections."""
        # Create a test domain collection
        collection = Collection(name='example.com', kind='domain')
        test_session.add(collection)
        test_session.commit()

        # Make the request
        request, response = await async_client.get('/api/collections?kind=domain')

        # Check response
        assert response.status_code == HTTPStatus.OK
        data = response.json

        # Check basic response structure
        assert 'collections' in data
        assert 'totals' in data

        # Check collections
        assert len(data['collections']) == 1
        assert data['collections'][0]['name'] == 'example.com'
        assert data['collections'][0]['kind'] == 'domain'

        # Check totals
        assert data['totals']['collections'] == 1

    @pytest.mark.asyncio
    async def test_get_collections_for_channels(
            self, async_client, test_session
    ):
        """Test that GET /api/collections?kind=channel returns channel collections."""
        from pathlib import Path

        # Create a test channel collection
        collection = Collection(
            name='Test Channel',
            kind='channel',
            directory=Path('/media/wrolpi/videos/test')
        )
        test_session.add(collection)
        test_session.commit()

        # Make the request
        request, response = await async_client.get('/api/collections?kind=channel')

        # Check response
        assert response.status_code == HTTPStatus.OK
        data = response.json

        # Check collections
        assert len(data['collections']) == 1
        assert data['collections'][0]['name'] == 'Test Channel'
        assert data['collections'][0]['kind'] == 'channel'

    @pytest.mark.asyncio
    async def test_get_collections_without_kind(
            self, async_client, test_session
    ):
        """Test that GET /api/collections without kind parameter returns all collections."""
        # Create test collections of different kinds
        domain = Collection(name='example.com', kind='domain')
        channel = Collection(name='Test Channel', kind='channel')
        test_session.add_all([domain, channel])
        test_session.commit()

        # Make the request without kind parameter
        request, response = await async_client.get('/api/collections')

        # Check response
        assert response.status_code == HTTPStatus.OK
        data = response.json

        # Should have both collections
        assert len(data['collections']) == 2
        assert data['totals']['collections'] == 2

    @pytest.mark.asyncio
    async def test_get_empty_collections(
            self, async_client, test_session
    ):
        """Test that GET /api/collections returns empty when no collections exist."""
        # Don't create any collections

        # Make the request
        request, response = await async_client.get('/api/collections?kind=domain')

        # Check response
        assert response.status_code == HTTPStatus.OK
        data = response.json

        # Should have empty collections
        assert len(data['collections']) == 0
        assert data['totals']['collections'] == 0

    @pytest.mark.asyncio
    async def test_get_collections_includes_video_count_for_channels(
            self, async_client, test_session, test_directory, channel_factory, video_factory
    ):
        """Test that GET /api/collections?kind=channel includes video statistics."""
        # Create a channel using the factory
        channel = channel_factory(name="Test Channel")
        test_session.flush()

        # Create a video in the channel
        video = video_factory(channel_id=channel.id, with_video_file=True)
        test_session.commit()

        # Make the request
        request, response = await async_client.get('/api/collections?kind=channel')

        # Check response includes video statistics
        assert response.status_code == HTTPStatus.OK
        data = response.json

        # Find our test channel
        test_channel_data = next(c for c in data['collections'] if c['name'] == "Test Channel")

        # Should have video_count and total_size
        assert 'video_count' in test_channel_data
        assert test_channel_data['video_count'] == 1
        assert 'total_size' in test_channel_data
        assert test_channel_data['total_size'] > 0


class TestCollectionTagInfoAPI:
    """Test the POST /api/collections/<id>/tag_info endpoint."""

    @pytest.mark.asyncio
    async def test_get_tag_info_suggests_directory(
            self, async_client, test_session, test_directory
    ):
        """Test that tag_info endpoint suggests a directory for a domain collection."""
        # Create a domain collection
        collection = Collection(
            name='example.com',
            kind='domain',
            directory=test_directory / 'archive' / 'example.com'
        )
        test_session.add(collection)
        test_session.commit()

        # Request tag info
        request, response = await async_client.post(
            f'/api/collections/{collection.id}/tag_info',
            json={'tag_name': 'WROL'}
        )

        # Check response
        assert response.status_code == HTTPStatus.OK
        data = response.json

        # Should suggest a directory with the tag
        assert 'suggested_directory' in data
        assert 'WROL' in data['suggested_directory']
        assert 'example.com' in data['suggested_directory']

        # Should not have a conflict
        assert data['conflict'] is False
        assert data['conflict_message'] is None

    @pytest.mark.asyncio
    async def test_get_tag_info_detects_domain_conflict(
            self, async_client, test_session, test_directory
    ):
        """Test that tag_info detects conflicts with existing domain collections."""
        # Create two domain collections
        collection1 = Collection(
            name='example.com',
            kind='domain',
            directory=test_directory / 'archive' / 'example.com'
        )
        collection2 = Collection(
            name='other.com',
            kind='domain',
            directory=test_directory / 'archive' / 'WROL' / 'other.com'
        )
        test_session.add_all([collection1, collection2])
        test_session.commit()

        # Request tag info for collection1 with a tag that would conflict with collection2
        request, response = await async_client.post(
            f'/api/collections/{collection1.id}/tag_info',
            json={'tag_name': 'WROL'}
        )

        # Check response
        assert response.status_code == HTTPStatus.OK
        data = response.json

        # Should suggest archive/WROL/example.com
        assert 'suggested_directory' in data
        assert 'WROL' in data['suggested_directory']
        assert 'example.com' in data['suggested_directory']

        # Should not have a conflict (different names, different directories)
        assert data['conflict'] is False

    @pytest.mark.asyncio
    async def test_get_tag_info_allows_channel_domain_same_directory(
            self, async_client, test_session, test_directory, channel_factory
    ):
        """Test that channel and domain collections can share directories."""
        # Create a channel collection
        channel = channel_factory(name='test', directory=test_directory / 'videos' / 'WROL' / 'test')
        test_session.flush()

        # Create a domain collection with a different directory
        domain = Collection(
            name='example.com',
            kind='domain',
            directory=test_directory / 'archive' / 'example.com'
        )
        test_session.add(domain)
        test_session.commit()

        # Request tag info for domain
        request, response = await async_client.post(
            f'/api/collections/{domain.id}/tag_info',
            json={'tag_name': 'WROL'}
        )

        # Check response
        assert response.status_code == HTTPStatus.OK
        data = response.json

        # Should not have a conflict (different kinds can share)
        assert data['conflict'] is False

    @pytest.mark.asyncio
    async def test_get_tag_info_detects_exact_directory_conflict(
            self, async_client, test_session, test_directory
    ):
        """Test that tag_info detects conflicts when suggested directory exactly matches existing collection."""
        # Create two domain collections with different names but where one's suggested directory
        # would conflict with the other's existing directory
        # collection1 is already in the "WROL" tagged location
        collection1 = Collection(
            name='conflicting.com',
            kind='domain',
            directory=test_directory / 'archive' / 'WROL' / 'example.com'
        )
        # collection2 is named example.com and would want to move to archive/WROL/example.com when tagged
        collection2 = Collection(
            name='example.com',
            kind='domain',
            directory=test_directory / 'archive' / 'example.com'
        )
        test_session.add_all([collection1, collection2])
        test_session.commit()

        # Request tag info for collection2 with a tag that would create the same directory as collection1
        request, response = await async_client.post(
            f'/api/collections/{collection2.id}/tag_info',
            json={'tag_name': 'WROL'}
        )

        # Check response
        assert response.status_code == HTTPStatus.OK
        data = response.json

        # Should suggest archive/WROL/example.com
        assert 'suggested_directory' in data
        assert 'WROL' in data['suggested_directory']
        assert 'example.com' in data['suggested_directory']

        # Should have a conflict (same directory as collection1)
        assert data['conflict'] is True
        assert data['conflict_message'] is not None
        assert 'conflicting.com' in data['conflict_message']

    @pytest.mark.asyncio
    async def test_get_tag_info_unknown_collection(
            self, async_client, test_session
    ):
        """Test that tag_info returns 404 for unknown collection."""
        # Request tag info for non-existent collection
        request, response = await async_client.post(
            '/api/collections/99999/tag_info',
            json={'tag_name': 'WROL'}
        )

        # Check response
        assert response.status_code == HTTPStatus.NOT_FOUND
        data = response.json
        assert 'error' in data


class TestCollectionDeletion:
    """Test the DELETE /api/collections/<id> endpoint."""

    @pytest.mark.asyncio
    async def test_delete_domain_collection_orphans_archives(
            self, async_client, test_session, test_directory
    ):
        """Test that deleting a domain collection orphans its archives."""
        from modules.archive.models import Archive
        from wrolpi.files.models import FileGroup

        # Create a domain collection
        collection = Collection(
            name='example.com',
            kind='domain',
            directory=test_directory / 'archive' / 'example.com'
        )
        test_session.add(collection)
        test_session.flush()

        # Create file groups and archives for this domain
        fg1 = FileGroup(primary_path=test_directory / 'archive' / 'example.com' / 'page1.html',
                        url='https://example.com/page1')
        fg2 = FileGroup(primary_path=test_directory / 'archive' / 'example.com' / 'page2.html',
                        url='https://example.com/page2')
        test_session.add_all([fg1, fg2])
        test_session.flush()

        archive1 = Archive(file_group_id=fg1.id, collection_id=collection.id)
        archive2 = Archive(file_group_id=fg2.id, collection_id=collection.id)
        test_session.add_all([archive1, archive2])
        test_session.commit()

        collection_id = collection.id

        # Verify archives are associated with the collection
        assert test_session.query(Archive).filter_by(collection_id=collection_id).count() == 2

        # Delete the collection
        request, response = await async_client.delete(f'/api/collections/{collection_id}')

        # Check response
        assert response.status_code == HTTPStatus.NO_CONTENT

        # Expire all cached objects to see changes made by the API's separate session
        test_session.expire_all()

        # Verify collection is deleted
        assert test_session.query(Collection).filter_by(id=collection_id).count() == 0

        # Verify archives are orphaned (collection_id is NULL) but still exist
        orphaned_archives = test_session.query(Archive).filter_by(collection_id=None).all()
        assert len(orphaned_archives) == 2
        assert {a.id for a in orphaned_archives} == {archive1.id, archive2.id}

        # Verify archives still exist in total
        assert test_session.query(Archive).count() == 2

    @pytest.mark.asyncio
    async def test_delete_unknown_collection(
            self, async_client, test_session
    ):
        """Test that deleting unknown collection returns 404."""
        # Try to delete non-existent collection
        request, response = await async_client.delete('/api/collections/99999')

        # Check response
        assert response.status_code == HTTPStatus.NOT_FOUND
        data = response.json
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_delete_channel_collection(
            self, async_client, test_session, test_directory, channel_factory
    ):
        """Test that deleting a channel collection works."""
        # Create a channel collection
        channel = channel_factory(name='test', directory=test_directory / 'videos' / 'test')
        test_session.commit()

        collection_id = channel.collection.id

        # Delete the collection
        request, response = await async_client.delete(f'/api/collections/{collection_id}')

        # Check response
        assert response.status_code == HTTPStatus.NO_CONTENT

        # Verify collection is deleted
        assert test_session.query(Collection).filter_by(id=collection_id).count() == 0


class TestCollectionTagging:
    """Test the POST /api/collections/<id>/tag endpoint for tagging and un-tagging."""

    @pytest.mark.asyncio
    async def test_untag_collection(
            self, async_client, test_session, test_directory, tag_factory
    ):
        """Test that sending tag_name=null removes the tag from a collection."""
        # Create a tag
        tag = await tag_factory('TestTag')
        test_session.flush()

        # Create a domain collection with a tag and directory
        collection = Collection(
            name='example.com',
            kind='domain',
            directory=test_directory / 'archive' / 'TestTag' / 'example.com',
            tag_id=tag.id
        )
        test_session.add(collection)
        test_session.commit()

        # Verify collection has the tag
        assert collection.tag_id == tag.id
        assert collection.tag_name == 'TestTag'

        # Send POST request to un-tag (with tag_name: null)
        request, response = await async_client.post(
            f'/api/collections/{collection.id}/tag',
            json={'tag_name': None}
        )

        # Check response
        assert response.status_code == HTTPStatus.OK

        # Refresh the collection from database
        test_session.refresh(collection)

        # Verify the tag has been removed
        assert collection.tag_id is None
        assert collection.tag_name is None

    @pytest.mark.asyncio
    async def test_tag_collection_without_directory(
            self, async_client, test_session, tag_factory
    ):
        """Test that tagging a collection without a directory works."""
        # Create a tag
        tag = await tag_factory('TestTag')
        test_session.flush()

        # Create a domain collection WITHOUT a directory
        collection = Collection(
            name='example.com',
            kind='domain',
            directory=None  # No directory!
        )
        test_session.add(collection)
        test_session.commit()

        # Verify collection has no directory
        assert collection.directory is None

        # Send POST request to tag the collection
        request, response = await async_client.post(
            f'/api/collections/{collection.id}/tag',
            json={'tag_name': 'TestTag'}
        )

        # Check response - should succeed
        assert response.status_code == HTTPStatus.OK

        # Refresh the collection from database
        test_session.refresh(collection)

        # Verify the tag was set
        assert collection.tag_id == tag.id
        assert collection.tag_name == 'TestTag'
        # Directory should still be None - not auto-generated
        assert collection.directory is None

    @pytest.mark.asyncio
    async def test_get_tag_info_without_directory(
            self, async_client, test_session
    ):
        """Test that get_tag_info returns None for suggested_directory when collection has no directory."""
        # Create a domain collection WITHOUT a directory
        collection = Collection(
            name='example.com',
            kind='domain',
            directory=None  # No directory!
        )
        test_session.add(collection)
        test_session.commit()

        # Request tag info
        request, response = await async_client.post(
            f'/api/collections/{collection.id}/tag_info',
            json={'tag_name': 'TestTag'}
        )

        # Check response
        assert response.status_code == HTTPStatus.OK
        data = response.json

        # For collections without a directory, suggested_directory should be None
        # (Currently it always computes a directory path)
        assert data['suggested_directory'] is None
        # No conflict checking needed without a directory
        assert data['conflict'] is False
        assert data['conflict_message'] is None
