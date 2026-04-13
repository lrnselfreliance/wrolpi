import pytest

from modules.docs.extractors import extract_epub, extract_pdf, extract_metadata, extract_docx, extract_odt, \
    extract_doc, extract_cbz, DocMetadata
from wrolpi.files.models import FileGroup


@pytest.mark.asyncio
async def test_extract_epub(test_session, test_directory, example_epub):
    """Metadata can be extracted from an EPUB file."""
    metadata = extract_epub(example_epub)
    assert metadata.title == 'WROLPi Test Book'
    assert metadata.author == 'roland'
    assert metadata.text  # Has text content.
    assert metadata.cover_bytes  # Has a cover image.


@pytest.mark.asyncio
async def test_extract_epub_sections(test_session, test_directory, example_epub):
    """extract_epub produces one DocSection per spine item with ascending ordinals."""
    metadata = extract_epub(example_epub)
    assert metadata.sections, 'EPUB should produce at least one section'
    assert all(s.kind == 'epub_spine' for s in metadata.sections)
    # Ordinals should be 0..N-1 and strictly ascending.
    ordinals = [s.ordinal for s in metadata.sections]
    assert ordinals == list(range(len(metadata.sections)))
    # Every section has a label.
    assert all(s.label for s in metadata.sections)


def test_resolve_spine_labels_carries_forward_across_split_chapters():
    """When a chapter spans multiple spine items (common in Calibre conversions),
    sections after the TOC-anchored one inherit the chapter label instead of
    falling back to a generic 'Section N'.

    This models real-world books like 'Mountain States Medicinal Plants' where each
    plant's chapter is split across ~5 spine items but the TOC only anchors the first.
    """
    from modules.docs.extractors import _resolve_spine_labels

    href_to_label = {
        'text/mullein_0.xhtml': 'Mullein',
        'text/yarrow_0.xhtml': 'Yarrow',
    }
    # (file_name, get_name) tuples in spine order.
    hrefs = [
        ('front.xhtml', 'front.xhtml'),
        ('text/mullein_0.xhtml', 'text/mullein_0.xhtml'),
        ('text/mullein_1.xhtml', 'text/mullein_1.xhtml'),
        ('text/mullein_2.xhtml', 'text/mullein_2.xhtml'),
        ('text/yarrow_0.xhtml', 'text/yarrow_0.xhtml'),
        ('text/yarrow_1.xhtml', 'text/yarrow_1.xhtml'),
    ]
    labels = _resolve_spine_labels(hrefs, href_to_label)

    # Front matter has no TOC anchor yet — falls back.
    assert labels[0] == 'Section 1'
    # mullein_0 is the TOC-anchored entry for 'Mullein'; the next two inherit it.
    assert labels[1:4] == ['Mullein', 'Mullein', 'Mullein']
    # yarrow_0 flips the carry-forward to the next chapter.
    assert labels[4:6] == ['Yarrow', 'Yarrow']


def test_build_epub_toc_label_map_strips_fragments_and_walks_nested():
    """_build_epub_toc_label_map handles fragments and nested (Section, [children])
    tuples, taking the first label that wins for a given href."""
    from modules.docs.extractors import _build_epub_toc_label_map

    class FakeLink:
        def __init__(self, href, title):
            self.href = href
            self.title = title

    toc = (
        FakeLink('chap1.xhtml', 'Chapter One'),
        # A nested (Section, [children]) tuple — children should be walked.
        (FakeLink('chap2.xhtml', 'Part Two'), [
            FakeLink('chap2.xhtml#sub-a', 'Sub A'),
            FakeLink('chap3.xhtml', 'Chapter Three'),
        ]),
        FakeLink('chap1.xhtml', 'Chapter One Duplicate'),  # first wins
    )
    result = _build_epub_toc_label_map(toc)
    assert result['chap1.xhtml'] == 'Chapter One'
    assert result['chap2.xhtml'] == 'Part Two'  # fragment stripped; first wins
    assert result['chap3.xhtml'] == 'Chapter Three'


@pytest.mark.asyncio
async def test_extract_pdf(test_session, test_directory, example_pdf):
    """Metadata can be extracted from a PDF file."""
    metadata = extract_pdf(example_pdf)
    # PDF may or may not have title metadata; at minimum it should return something.
    assert metadata is not None
    assert isinstance(metadata, DocMetadata)


@pytest.mark.asyncio
async def test_extract_pdf_metadata(test_session, test_directory, example_pdf):
    """PDF extractor extracts page count, date, cover, and text."""
    metadata = extract_pdf(example_pdf)
    assert metadata.title == 'WROLPi Test PDF'
    assert metadata.author == 'roland'
    assert metadata.page_count == 3
    assert metadata.published_date is not None
    assert metadata.cover_bytes
    assert metadata.text


@pytest.mark.asyncio
async def test_extract_pdf_sections(test_session, test_directory, example_pdf):
    """extract_pdf produces one DocSection per page with 1-based ordinals."""
    metadata = extract_pdf(example_pdf)
    assert metadata.sections, 'PDF should produce at least one section'
    assert all(s.kind == 'pdf_page' for s in metadata.sections)
    # Pages are 1-indexed; the test PDF has 3 pages.
    assert [s.ordinal for s in metadata.sections] == [1, 2, 3]
    assert all(s.label == f'Page {s.ordinal}' for s in metadata.sections)


@pytest.mark.asyncio
async def test_extract_docx(test_session, test_directory, example_docx):
    """DOCX extractor extracts text content."""
    metadata = extract_docx(example_docx)
    assert isinstance(metadata, DocMetadata)
    assert metadata.title == 'Word Document'
    assert metadata.text
    assert 'Example Word Document' in metadata.text


@pytest.mark.asyncio
async def test_extract_odt(test_session, test_directory, example_odt):
    """ODT extractor extracts title and text."""
    metadata = extract_odt(example_odt)
    assert metadata.title is not None
    assert metadata.text
    assert 'Test Header' in metadata.text


@pytest.mark.asyncio
async def test_extract_doc(test_session, test_directory, example_doc):
    """DOC extractor extracts title from filename and text if catdoc/textutil available."""
    metadata = extract_doc(example_doc)
    assert metadata.title  # At minimum, title from filename.


@pytest.mark.asyncio
async def test_extract_cbz(test_session, test_directory, example_cbz):
    """CBZ extractor extracts cover image."""
    metadata = extract_cbz(example_cbz)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_cbz_comicinfo(test_session, test_directory, example_cbz_metadata):
    """CBZ extractor reads ComicInfo.xml metadata."""
    metadata = extract_cbz(example_cbz_metadata)
    assert metadata.title == 'Bobby Make-Believe #1'
    assert metadata.author == 'Frank King'
    assert metadata.publisher == 'Chicago Tribune'
    assert metadata.description == 'Bobby Make-Believe is a comic strip by Frank King.'
    assert metadata.language == 'en'
    assert metadata.subject == 'Comic Strip'
    assert metadata.page_count == 4
    assert metadata.published_date.year == 1915
    assert metadata.published_date.month == 6
    assert metadata.published_date.day == 15
    assert metadata.cover_bytes is not None


@pytest.mark.asyncio
async def test_extract_cbt(test_session, test_directory, example_cbt):
    """CBT (TAR) extractor extracts cover image."""
    metadata = extract_cbz(example_cbt)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_cbr(test_session, test_directory, example_cbr):
    """CBR (RAR) extractor extracts cover image."""
    metadata = extract_cbz(example_cbr)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_cb7(test_session, test_directory, example_cb7):
    """CB7 (7z) extractor extracts cover image."""
    metadata = extract_cbz(example_cb7)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_metadata_cbt(test_session, test_directory, example_cbt):
    """extract_metadata dispatches CBT files to the comic extractor."""
    fg = FileGroup.from_paths(test_session, example_cbt)
    test_session.flush()
    metadata = extract_metadata(fg)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_metadata_cb7(test_session, test_directory, example_cb7):
    """extract_metadata dispatches CB7 files to the comic extractor."""
    fg = FileGroup.from_paths(test_session, example_cb7)
    test_session.flush()
    metadata = extract_metadata(fg)
    assert metadata.cover_bytes is not None
    assert len(metadata.cover_bytes) > 0


@pytest.mark.asyncio
async def test_extract_metadata_dispatches(test_session, test_directory, example_epub):
    """extract_metadata dispatches to the correct extractor based on mimetype."""
    fg = FileGroup.from_paths(test_session, example_epub)
    test_session.flush()

    metadata = extract_metadata(fg)
    assert metadata.title == 'WROLPi Test Book'
    assert metadata.author == 'roland'
