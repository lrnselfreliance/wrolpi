import json
import shutil
from http import HTTPStatus

import pytest

from wrolpi.files.ebooks import EBook, EPUB_MIMETYPE
from wrolpi.files.lib import refresh_files, move
from wrolpi.files.models import FileGroup
from wrolpi.test.common import assert_dict_contains


@pytest.mark.asyncio
async def test_index(async_client, test_session, test_directory, example_epub, example_mobi):
    """Ebooks can be indexed.

    Covers can be discovered."""
    await refresh_files()

    ebook: EBook = test_session.query(EBook).one()

    assert ebook.file_group.title == 'WROLPi Test Book'
    assert ebook.file_group.mimetype.startswith(EPUB_MIMETYPE)
    assert ebook.file_group.author == 'roland'
    assert ebook.size == 292579
    assert ebook.file_group.data == {'author': 'roland', 'title': 'WROLPi Test Book',
                                     'cover_path': test_directory / 'ebook example.jpeg',
                                     'ebook_path': test_directory / 'ebook example.epub',
                                     }

    assert ebook.file_group.a_text, 'Book title was not indexed'
    assert ebook.file_group.b_text, 'Book author was not indexed'
    assert ebook.file_group.d_text, 'Book text was not indexed'
    # Both ebooks are assumed to be the same book, but different formats.
    assert (epubs := ebook.file_group.my_files('application/epub+zip')) and len(epubs) == 1 \
           and epubs[0]['path'] == example_epub
    assert (mobis := ebook.file_group.my_files('application/x-mobipocket-ebook')) and len(mobis) == 1 \
           and mobis[0]['path'] == example_mobi
    # Cover was discovered.
    assert len(ebook.file_group.my_poster_files()) == 1
    # EPUB, MOBI, JPEG.
    assert len(ebook.file_group.files) == 3

    # Ebooks can be deleted during refresh.
    example_epub.unlink()
    await refresh_files()
    assert test_session.query(EBook).count() == 1
    ebook = test_session.query(EBook).one()
    assert not ebook.file_group.my_files('application/epub+zip')
    assert (mobis := ebook.file_group.my_files('application/x-mobipocket-ebook')) and len(mobis) == 1 \
           and mobis[0]['path'] == example_mobi
    # Cover was discovered.
    assert len(ebook.file_group.my_poster_files()) == 1
    # MOBI, JPEG.
    assert len(ebook.file_group.files) == 2


@pytest.mark.asyncio
async def test_discover_local_cover(test_session, test_directory, example_epub, image_bytes_factory, await_switches):
    cover_path = example_epub.with_suffix('.jpg')
    cover_path.write_bytes(image_bytes_factory())
    await refresh_files()

    ebook: EBook = test_session.query(EBook).one()

    # Cover file near the eBook was discovered.
    assert ebook.cover_path.read_bytes() == cover_path.read_bytes()


@pytest.mark.asyncio
async def test_extract_cover(test_session, test_directory, example_epub, await_switches):
    """First image is extracted from the Ebook and used as the cover."""
    await refresh_files()

    ebook: EBook = test_session.query(EBook).one()
    # The WROLPi logo is the first image in the example epub.
    assert ebook.cover_path and ebook.cover_path.stat().st_size == 297099


def test_search_ebooks(test_session, test_client, example_epub):
    """Ebooks are handled in File search results."""
    request, response = test_client.post('/api/files/refresh')
    assert response.status_code == HTTPStatus.NO_CONTENT

    assert test_session.query(EBook).count() == 1

    ebook: EBook = test_session.query(EBook).one()
    assert ebook.file_group.title == 'WROLPi Test Book'
    assert ebook.file_group.author == 'roland'
    assert ebook.file_group.a_text == 'WROLPi Test Book', 'Book title was not updated'
    assert ebook.file_group.d_text, 'Book was not indexed'

    content = dict(mimetypes=['application/epub', 'application/x-mobipocket-ebook'])
    request, response = test_client.post('/api/files/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json
    file_group = response.json['file_groups'][0]
    epub_file = file_group['files'][0]
    assert epub_file['path'] == 'ebook example.epub' and epub_file['mimetype'] == 'application/epub+zip'
    assert_dict_contains(
        file_group['data'],
        {'cover_path': 'ebook example.jpeg', 'ebook_path': 'ebook example.epub', 'title': 'WROLPi Test Book',
         'author': 'roland'},
    )

    # No Mobi ebook.
    content = dict(mimetypes=['application/x-mobipocket-ebook'])
    request, response = test_client.post('/api/files/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json
    assert len(response.json['file_groups']) == 0


@pytest.mark.asyncio
async def test_discover_calibre_cover(test_session, test_directory, example_epub, example_mobi, image_file):
    """Calibre puts a cover near an ebook file, test if it can be found."""
    # Create a Calibre metadata file.
    metadata = test_directory / 'metadata.opf'
    metadata.touch()

    # Create a "cover.jpg" file near the ebook, this is the Calibre cover.
    cover_image = test_directory / 'cover.jpg'
    shutil.move(image_file, cover_image)

    # Calibre cover image was discovered, no cover was generated.
    await refresh_files()
    ebook: EBook = test_session.query(EBook).one()
    assert ebook.file_group.title == 'WROLPi Test Book'
    assert ebook.cover_file['path'] == test_directory / 'cover.jpg'
    assert {i['path'].name for i in ebook.file_group.files} == {'ebook example.epub', 'ebook example.mobi', 'cover.jpg'}
    # Cover is not the first image from the EPUB.
    assert ebook.cover_path.stat().st_size != 292579
    # Metadata and cover were deleted from the FileGroups.
    assert test_session.query(FileGroup).count() == 1


@pytest.mark.asyncio
async def test_move_ebook(async_client, test_session, test_directory, example_epub, image_file, tag_factory):
    """An ebook is re-indexed when moved."""
    tag = await tag_factory()
    shutil.move(image_file, example_epub.with_suffix('.jpg'))
    await refresh_files()

    ebook: EBook = test_session.query(EBook).one()
    assert ebook.cover_path
    assert_dict_contains(ebook.file_group.data, dict(author='roland'))
    assert sorted([i['path'] for i in ebook.file_group.files]) == [
        test_directory / 'ebook example.epub',
        test_directory / 'ebook example.jpg',
    ]
    ebook.file_group.add_tag(tag.id)
    test_session.commit()

    new_directory = test_directory / 'new'
    new_directory.mkdir()
    await move(new_directory, ebook.file_group.primary_path)

    ebook: EBook = test_session.query(EBook).one()
    assert ebook.file_group.primary_path == test_directory / 'new/ebook example.epub'
    assert ebook.cover_path
    assert_dict_contains(ebook.file_group.data, dict(author='roland'))
    assert sorted([i['path'] for i in ebook.file_group.files]) == [
        test_directory / 'new/ebook example.epub',
        test_directory / 'new/ebook example.jpg',
    ]
