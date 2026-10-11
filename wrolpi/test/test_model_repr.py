import pytest

from modules.docs.conftest import doc_factory  # noqa: F401  The docs module's fixture.
from modules.repos.models import Repository
from modules.zim.models import TagZimEntry
from wrolpi.collections import Collection
from wrolpi.db import no_db_access
from wrolpi.downloader import Download


@pytest.fixture
def every_model(async_client, test_session, video_factory, channel_factory, archive_factory, doc_factory, zim_factory,
                tag_factory):
    """One saved instance of each model that has a `__repr__`, plus the related rows its repr describes."""

    async def _():
        tag = await tag_factory('one')
        channel = channel_factory()
        video = video_factory(channel_id=channel.id, title='a video', tag_names=['one'])
        archive = archive_factory('example.com', 'https://example.com/page')
        doc = doc_factory()
        zim = zim_factory('test zim')
        tag_zim_entry = TagZimEntry(tag=tag, zim=zim, zim_entry='home')
        repository = Repository(url='https://example.com/owner/repo.git',
                                collection=Collection(kind='repo', name='repo'))
        download = Download(url='https://example.com/feed', downloader='rss', frequency=86400,
                            collection=channel.collection)
        test_session.add_all([tag_zim_entry, repository, download])
        test_session.commit()
        models = [tag, channel, channel.collection, download, video, video.file_group,
                  *video.file_group.tag_files, archive, archive.collection, doc, zim, tag_zim_entry, repository]
        return {type(i).__name__: i for i in models}

    return _


@pytest.mark.asyncio
async def test_repr_runs_no_sql(test_session, every_model):
    """A repr reads only what is loaded.  Reprs run inside log calls, where a query (or a refresh after commit)
    is a hidden round trip, and on an object whose session is gone it raises instead of logging."""
    models = await every_model()
    assert {'Tag', 'TagFile', 'Channel', 'Collection', 'Download', 'Video', 'FileGroup', 'Archive', 'Doc', 'Zim',
            'TagZimEntry', 'Repository'} <= set(models)

    test_session.expire_all()  # As after a commit in a background session.
    with no_db_access('repr'):
        reprs = {name: repr(model) for name, model in models.items()}
    assert all(i.startswith(f'<{name}') for name, i in reprs.items()), reprs

    test_session.expunge_all()  # Detached and expired: the session is gone.
    for name, model in models.items():
        assert repr(model).startswith(f'<{name}'), name


@pytest.mark.asyncio
async def test_repr_describes_loaded_objects(test_session, every_model):
    """With everything loaded, a repr still shows the related names and paths."""
    models = await every_model()
    # Load what each repr describes, as the code that logs these objects would have.
    video, tag_file, archive = models['Video'], models['TagFile'], models['Archive']
    assert video.file_group.title and tag_file.tag.name and archive.file_group.url and archive.collection.name
    assert models['Doc'].file_group.primary_path and models['TagZimEntry'].tag.name
    assert models['Channel'].collection.name

    assert "title='a video'" in repr(models['Video'])
    assert 'tag=one' in repr(models['TagFile'])
    assert 'url=https://example.com/page' in repr(models['Archive'])
    assert 'domain=example.com' in repr(models['Archive'])
    assert "path='" in repr(models['Doc']) and 'None' not in repr(models['Doc'])
    assert "tag='one'" in repr(models['TagZimEntry'])
    assert models['Channel'].name in repr(models['Channel'])
