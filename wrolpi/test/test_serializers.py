"""Serializers read only data that is already loaded (see `wrolpi.db.no_db_access`).

A lazy load while serializing is a hidden query per row, and a `MissingGreenlet` error under an async Session.
The relationships each serializer reads are loaded with their parent (`lazy='joined'` / `'selectin'`).
"""
import pytest
from sqlalchemy.orm import undefer

from modules.archive.models import Archive
from modules.docs.models import Doc
from modules.videos.models import Channel, Video
from modules.zim.models import Zim, ZimSubscription
from wrolpi.collections.models import Collection, CollectionItem
from wrolpi.conftest import production_like_sessions
from wrolpi.db import no_db_access
from wrolpi.downloader import Download
from wrolpi.files.models import FileGroup
from wrolpi.tags import Tag


@pytest.mark.asyncio
async def test_models_serialize_without_queries(async_client, test_session, tag_factory, simple_channel,
                                                video_factory, archive_factory, zim_factory, test_downloader,
                                                test_directory):
    tag = await tag_factory()
    video = video_factory(title='a video', channel_id=simple_channel.id)
    video.file_group.add_tag(test_session, tag.name)
    archive_factory(domain='example.com')
    doc_path = test_directory / 'manual.pdf'
    doc_path.write_bytes(b'%PDF-1.4 test')
    test_session.add(Doc(file_group=FileGroup.from_paths(test_session, doc_path)))
    zim_factory('wikipedia.zim')
    simple_channel.collection.tag = tag
    download = Download(url='https://example.com/channel', downloader=test_downloader.name, frequency=3600,
                        collection_id=simple_channel.collection_id)
    test_session.add(download)
    test_session.flush()
    test_session.add(ZimSubscription(name='Wikipedia', language='en', download_id=download.id))
    test_session.commit()

    _, response = await async_client.post('/api/collections', json={'name': 'Mixed'})
    playlist_id = response.json['collection']['id']
    for body in ({'item_kind': 'file', 'file_group_id': video.file_group_id},
                 {'item_kind': 'url', 'url': '/videos', 'title': 'Videos'}):
        await async_client.post(f'/api/collections/{playlist_id}/items', json=body)

    with production_like_sessions(test_session) as maker:
        session = maker()
        for model in (FileGroup, Video, Archive, Doc, Zim, ZimSubscription, Collection, Channel, Tag, Download):
            query = session.query(model)
            if model is Video:
                # Like the queries that serialize Videos: the codecs come from the deferred ffprobe_json.
                query = query.options(undefer(Video.ffprobe_json))
            objects = query.all()
            assert objects, f'no {model.__name__} to serialize'
            with no_db_access(f'serializing {model.__name__}'):
                for obj in objects:
                    obj.__json__()

        items = session.query(CollectionItem).all()
        assert len(items) == 2
        with no_db_access('serializing CollectionItem'):
            serialized = [item.dict() for item in items]
        assert serialized[0]['file_group']['tags'] == [tag.name]
