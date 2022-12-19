import pytest

from wrolpi.files.lib import refresh_files
from wrolpi.files.models import File


@pytest.mark.asyncio
async def test_pdf_title(test_session, example_pdf):
    """PDF modeler extracts the PDF's title."""
    await refresh_files()

    pdf: File = test_session.query(File).one()
    assert pdf.title == 'WROLPi Test PDF'
