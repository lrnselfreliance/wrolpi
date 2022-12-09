import json
import shutil
from http import HTTPStatus

import pytest

from wrolpi.files.ebooks import EBook, MOBI_MIMETYPE, EPUB_MIMETYPE
from wrolpi.files.lib import refresh_files
from wrolpi.test.common import assert_dict_contains


@pytest.mark.asyncio
async def test_index(test_session, test_directory, example_epub, example_mobi):
    """Ebooks can be indexed.

    Covers can be discovered."""
    await refresh_files()

    ebook_epub, ebook_mobi = test_session.query(EBook).order_by(EBook.ebook_path)
    ebook_epub: EBook
    ebook_mobi: EBook

    assert ebook_epub.title == 'WROLPi Test Book'
    assert ebook_epub.ebook_file.mimetype.startswith(EPUB_MIMETYPE)
    assert ebook_epub.creator == 'roland'
    assert ebook_epub.size == ebook_epub.ebook_file.size
    assert ebook_epub.cover_path and ebook_epub.cover_path.is_file()
    # The cover is the WROLPi logo.
    assert ebook_epub.cover_file.size == 297099

    assert ebook_epub.ebook_file.a_text, 'Book title was not indexed'
    assert ebook_epub.ebook_file.b_text, 'Book creator was not indexed'
    assert ebook_epub.ebook_file.d_text, 'Book text was not indexed'

    # Mobi is not fully supported, title is the file name.  No creator or cover.
    assert ebook_mobi.title == 'example'
    assert ebook_mobi.ebook_file.mimetype == MOBI_MIMETYPE
    assert not ebook_mobi.creator
    assert not ebook_mobi.cover_path

    # Ebooks can be deleted during refresh.
    example_mobi.unlink()
    example_epub.unlink()
    await refresh_files()
    assert test_session.query(EBook).count() == 0


def test_search(test_session, test_client, example_epub):
    """Ebooks are handled in File search results."""
    request, response = test_client.post('/api/files/refresh')
    assert response.status == HTTPStatus.NO_CONTENT

    assert test_session.query(EBook).count() == 1

    ebook: EBook = test_session.query(EBook).one()
    assert ebook.title == 'WROLPi Test Book'
    assert ebook.creator == 'roland'
    assert ebook.ebook_file.a_text == 'WROLPi Test Book', 'Book title was not updated'
    assert ebook.ebook_file.d_text, 'Book was not indexed'

    content = dict(mimetypes=['application/epub', 'application/x-mobipocket-ebook'])
    request, response = test_client.post('/api/files/search', content=json.dumps(content))
    assert response.status == HTTPStatus.OK
    assert response.json
    result = response.json['files'][0]
    assert result['path'] == 'example.epub'
    assert result['mimetype'] == 'application/epub+zip'
    assert_dict_contains(
        result['ebook'],
        {'cover_path': 'example.jpeg', 'ebook_path': 'example.epub'},
    )

    content = dict(mimetypes=['application/epub+zip', 'application/x-mobipocket-ebook'])
    request, response = test_client.post('/api/files/search', content=json.dumps(content))
    result = response.json['files'][0]
    assert result['path'] == 'example.epub'
    assert result['mimetype'] == 'application/epub+zip'

    content = dict(mimetypes=[])
    request, response = test_client.post('/api/files/search', content=json.dumps(content))
    assert response.status == HTTPStatus.OK
    assert response.json


@pytest.mark.asyncio
async def test_discover_calibre_cover(test_session, test_directory, example_epub, image_file):
    """Calibre puts a cover near an ebook file, test if it can be found."""
    # Create two files in the
    metadata = test_directory / 'metadata.opf'
    metadata.touch()
    # Create an alternate format next to the epub.  This will be ignored because it is not yet supported.
    mobi_path = example_epub.with_suffix('.mobi')
    mobi_path.touch()

    await refresh_files()

    assert test_session.query(EBook).count() == 1
    ebook: EBook = test_session.query(EBook).one()
    assert ebook.title == 'WROLPi Test Book'
    # The cover in the ebook was extracted.
    assert ebook.cover_file.size == 297099

    # Delete the extracted cover, use the cover image from Calibre.
    ebook.cover_path.unlink()
    test_session.delete(ebook.cover_file)
    cover_image = test_directory / 'cover.jpg'
    shutil.move(image_file, cover_image)

    # Calibre cover image was discovered, no cover was generated.
    await refresh_files()
    ebook: EBook = test_session.query(EBook).one()
    assert ebook.title == 'WROLPi Test Book'
    assert ebook.cover_file.size == 641

    # Create a file nearby, its no longer a Calibre directory.
    mobi_path = mobi_path.rename(test_directory / 'other book.mobi')
    await refresh_files()
    assert ebook.title == 'WROLPi Test Book'
    assert ebook.cover_file.size == 297099
    mobi_path.unlink()

    # Delete the discovered cover, cover should be generated.
    cover_image.unlink()
    await refresh_files()
    ebook: EBook = test_session.query(EBook).one()
    assert ebook.title == 'WROLPi Test Book'
    assert ebook.cover_file.size == 297099
