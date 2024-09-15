from unittest import mock

import pytest

from wrolpi.dates import now
from wrolpi.files import lib as files_lib
from wrolpi.files import pdfs
from wrolpi.files.models import FileGroup


@pytest.mark.asyncio
async def test_pdf_title(async_client, test_session, example_pdf):
    """PDF modeler extracts a PDFs title and contents."""
    await files_lib.refresh_files()

    with mock.patch('wrolpi.files.pdfs.get_pdf_metadata') as mock_get_pdf_metadata:
        mock_get_pdf_metadata.side_effect = Exception('Should not index twice')
        await files_lib.refresh_files()

    pdf: FileGroup = test_session.query(FileGroup).one()
    assert pdf.indexed is True
    assert pdf.title == pdf.a_text == 'WROLPi Test PDF'
    assert pdf.b_text == 'roland'
    assert pdf.c_text == 'pdf example pdf'
    assert pdf.d_text and pdf.d_text.startswith('Page one\n') and len(pdf.d_text) == 467
    # Metadata within the PDF.
    assert pdf.author
    assert pdf.published_datetime
    # The date the file was modified.
    assert pdf.modification_datetime


@pytest.mark.asyncio
async def test_pdf_modeler(test_session, example_pdf):
    """PDFs can be indexed by PDFIndexer."""
    files_lib._upsert_files([example_pdf], now())

    await pdfs.pdf_modeler()
    file_group = test_session.query(FileGroup).one()
    a_text, b_text, c_text, d_text = file_group.a_text, file_group.b_text, file_group.c_text, file_group.d_text

    # The title extracted from the PDF.
    assert a_text == 'WROLPi Test PDF'
    # The author.
    assert b_text == 'roland'
    # The parsed file name.
    assert c_text == 'pdf example pdf'
    # All pages are extracted.  Text is formatted to fit on vertical screen.
    assert d_text == 'Page one\n' \
                     'Page two\n' \
                     'Lorem ipsum dolor sit amet,\n' \
                     'consectetur adipiscing elit, sed do\n' \
                     'eiusmod tempor incididunt ut labore et\n' \
                     '\n' \
                     'dolore magna aliqua. Ut enim ad minim\n' \
                     'veniam, quis nostrud exercitation\n' \
                     'ullamco laboris nisi ut \n' \
                     'aliquip ex ea commodo consequat. Duis\n' \
                     'aute irure dolor in reprehenderit in\n' \
                     'voluptate velit esse cillum \n' \
                     'dolore eu fugiat nulla pariatur.\n' \
                     'Excepteur sint occaecat cupidatat non\n' \
                     'proident, sunt in culpa qui officia \n' \
                     'deserunt mollit anim id est laborum.'


@pytest.mark.asyncio
async def test_pdf_indexer_max_size(test_session, example_pdf):
    """The contents of a large PDF are not indexed."""
    example_pdf.write_bytes(example_pdf.read_bytes() * 5000)

    files_lib._upsert_files([example_pdf], now())

    await pdfs.pdf_modeler()
    file_group = test_session.query(FileGroup).one()
    assert file_group.d_text is None
