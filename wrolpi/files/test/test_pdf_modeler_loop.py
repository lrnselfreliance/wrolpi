"""Test for pdf_modeler loop to ensure it processes more than one batch.

This test ensures the pdf_modeler can process more than PDF_PROCESSING_LIMIT (10)
files. If the loop logic has an off-by-one error (like using enumerate() with wrong
comparison), the modeler would only process one batch and exit early.
"""
import shutil

import pytest

from wrolpi.files.pdfs import pdf_modeler, PDF_PROCESSING_LIMIT
from wrolpi.files.models import FileGroup
from wrolpi.vars import PROJECT_DIR


@pytest.mark.asyncio
async def test_pdf_modeler_processes_more_than_batch_limit(async_client, test_session, test_directory):
    """
    Test that pdf_modeler processes MORE than PDF_PROCESSING_LIMIT (10) files.

    This test creates 15 PDF files and verifies that pdf_modeler
    processes all of them, not just the first batch of 10.

    This catches off-by-one bugs in the loop logic (e.g., using enumerate()
    which is 0-indexed but comparing against the limit incorrectly).
    """
    pdf_dir = test_directory / 'pdfs'
    pdf_dir.mkdir(parents=True)

    # Create more PDFs than the batch limit
    num_pdfs = PDF_PROCESSING_LIMIT + 5  # 15 PDFs
    pdf_paths = []

    for i in range(num_pdfs):
        pdf_path = pdf_dir / f'test_pdf_{i:03d}.pdf'
        shutil.copy(PROJECT_DIR / 'test/pdf example.pdf', pdf_path)
        pdf_paths.append(pdf_path)

    # Create FileGroups for each PDF file (simulating what refresh does)
    for pdf_path in pdf_paths:
        fg = FileGroup.from_paths(test_session, pdf_path)
        assert fg.mimetype == 'application/pdf'

    test_session.commit()

    # Verify we have the expected number of unindexed PDF FileGroups
    unindexed_count = test_session.query(FileGroup).filter(
        FileGroup.indexed != True,
        FileGroup.mimetype == 'application/pdf',
    ).count()
    assert unindexed_count == num_pdfs, f"Expected {num_pdfs} unindexed PDF files, got {unindexed_count}"

    # Run the pdf_modeler
    await pdf_modeler()

    # Count how many FileGroups are now indexed as PDFs
    indexed_pdf_count = test_session.query(FileGroup).filter(
        FileGroup.indexed == True,
        FileGroup.model == 'pdf',
    ).count()

    # All PDFs should be indexed
    assert indexed_pdf_count == num_pdfs, \
        f"pdf_modeler should process ALL {num_pdfs} files, but only processed {indexed_pdf_count}. " \
        f"This may be an off-by-one bug in the loop logic!"

    # Also verify no FileGroups remain unindexed
    still_unindexed = test_session.query(FileGroup).filter(
        FileGroup.indexed != True,
        FileGroup.mimetype == 'application/pdf',
    ).count()
    assert still_unindexed == 0, \
        f"All PDF FileGroups should be indexed, but {still_unindexed} remain unindexed"
