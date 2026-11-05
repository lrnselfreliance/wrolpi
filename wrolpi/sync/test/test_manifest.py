import os

import pytest

from wrolpi.files.models import FileGroup
from wrolpi.sync import lib


@pytest.mark.asyncio
async def test_manifest_pages(async_client, test_session, test_directory, make_files_structure, refresh_files):
    """The manifest lists every file of every FileGroup, a page of FileGroups at a time, in id order."""
    make_files_structure({f'docs/{i}.txt': f'file {i}' for i in range(7)})
    await refresh_files()

    pages = list()
    after_id = 0
    while after_id is not None:
        page = lib.build_manifest_page(test_session, after_id, limit=3)
        pages.append(page)
        after_id = page['next_after_id']

    assert [len(i['groups']) for i in pages] == [3, 3, 1]
    ids = [g['id'] for page in pages for g in page['groups']]
    assert ids == sorted(ids)
    assert pages[0]['max_id'] == max(ids)

    files = {p['path']: p for page in pages for g in page['groups'] for p in g['paths']}
    assert set(files) == {f'docs/{i}.txt' for i in range(7)}
    stat = (test_directory / 'docs/3.txt').stat()
    assert files['docs/3.txt']['size'] == stat.st_size
    assert files['docs/3.txt']['mtime'] == stat.st_mtime


def test_manifest_skips(test_session, test_directory):
    """Files that are still downloading, hidden, missing, or outside the library are not listed."""
    directory = test_directory / 'videos'
    directory.mkdir()
    for name in ('video.mp4', 'video.mp4.part', 'video.f137.mp4', 'video.mp4.aria2', '.video.mp4.partial',
                 'video.en.vtt'):
        (directory / name).write_text(name)
    outside = test_directory.parent / f'{test_directory.name}-outside.txt'
    outside.write_text('outside')
    try:
        group = FileGroup.from_paths(test_session, directory / 'video.mp4', directory / 'video.en.vtt')
        group.files = [
            *group.files,
            dict(path='video.mp4.part'), dict(path='video.f137.mp4'), dict(path='video.mp4.aria2'),
            dict(path='.video.mp4.partial'), dict(path='deleted.mp4'),
            # Older rows stored absolute paths.
            dict(path=str(directory / 'video.en.vtt')),
            dict(path=str(outside)),
            {},
        ]
        test_session.commit()

        page = lib.build_manifest_page(test_session)
    finally:
        os.remove(outside)

    paths = [p['path'] for g in page['groups'] for p in g['paths']]
    assert sorted(set(paths)) == ['videos/video.en.vtt', 'videos/video.mp4']
    assert page['next_after_id'] is None


def test_manifest_empty(test_session, test_directory):
    assert lib.build_manifest_page(test_session) == dict(groups=[], next_after_id=None, max_id=0,
                                                         limit=lib.MANIFEST_PAGE_LIMIT)
