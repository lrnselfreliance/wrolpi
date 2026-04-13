import dataclasses
import datetime
import logging
import os
import pathlib
import zipfile
from typing import List

import pytz

from wrolpi import dates
from wrolpi.common import truncate_generator_bytes, truncate_object_bytes, get_html_soup
from wrolpi.files.indexers import Indexer
from wrolpi.files.models import FileGroup
from wrolpi.vars import FILE_MAX_PDF_SIZE, FILE_MAX_TEXT_SIZE

# Cap on a single section's stored text to prevent a pathological one-chapter-is-the-whole-book
# EPUB from producing a huge row.
SECTION_MAX_TEXT_SIZE = 200_000

try:
    import ebooklib
    from ebooklib import epub
except ImportError:
    ebooklib = None
    epub = None

try:
    import pymupdf
except ImportError:
    pymupdf = None

try:
    import docx
except ImportError:
    docx = None

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class DocSection:
    """A searchable sub-range of a document (EPUB spine item or PDF page).

    `ordinal` is 0-based for EPUB spine items and 1-based for PDF pages, to match the
    conventions of the respective viewers.
    """
    kind: str  # 'epub_spine' or 'pdf_page'
    ordinal: int
    label: str
    content: str


@dataclasses.dataclass
class DocMetadata:
    title: str = None
    author: str = None
    publisher: str = None
    published_date: datetime.datetime = None
    page_count: int = None
    language: str = None
    subject: str = None
    description: str = None
    cover_bytes: bytes = None
    text: str = None
    sections: List[DocSection] = dataclasses.field(default_factory=list)


def extract_metadata(file_group: FileGroup) -> DocMetadata:
    """Extract metadata from a FileGroup based on its mimetype."""
    mimetype = file_group.mimetype or ''
    path = file_group.primary_path

    if mimetype.startswith('application/epub'):
        return extract_epub(path)
    elif mimetype == 'application/x-mobipocket-ebook':
        # MOBI files can't be easily parsed for metadata.
        return DocMetadata(title=Indexer.get_title(path))
    elif mimetype == 'application/pdf':
        return extract_pdf(path)
    elif mimetype == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        return extract_docx(path)
    elif mimetype == 'application/msword':
        return extract_doc(path)
    elif mimetype == 'application/vnd.oasis.opendocument.text':
        return extract_odt(path)
    elif mimetype in ('application/vnd.comicbook+zip', 'application/x-cbz',
                      'application/vnd.comicbook-rar', 'application/x-cbr'):
        return extract_cbz(path)
    elif path.suffix.lower() in ('.cbz', '.cbr', '.cbt', '.cb7'):
        return extract_cbz(path)

    return DocMetadata(title=Indexer.get_title(path))


def _extract_text_from_html(html: str) -> str:
    soup = get_html_soup(html)
    return soup.get_text()


def _build_epub_toc_label_map(toc) -> dict:
    """Walk an ebooklib TOC (nested list of Links and (Section, children) tuples)
    and return a mapping of href (fragment-stripped) -> label.

    The first label wins for any given href; children are walked so deeply-nested
    entries still contribute. Anything without both an href and a title is skipped.
    """
    href_to_label: dict = {}

    def walk(entries):
        for entry in entries or ():
            if isinstance(entry, (list, tuple)):
                walk(entry)
            else:
                href = getattr(entry, 'href', None)
                title = getattr(entry, 'title', None)
                if href and title:
                    href_to_label.setdefault(href.split('#')[0], title)

    walk(toc)
    return href_to_label


def _iter_epub_spine_documents(book) -> list:
    """Return the EpubHtml items that make up the book's reading spine, in order.

    Using `book.get_items_of_type(ITEM_DOCUMENT)` is wrong for deep-linking because
    it enumerates the full manifest — which can include EPUB 3 `nav.xhtml` files
    (excluded from the spine) and can return items in manifest order that differs
    from spine order. The viewer (`epub.html`) resolves deep-links via
    `spine.get(n)`, which indexes the reading spine only — so section ordinals
    must match that.

    Falls back to the manifest-order iteration only if the book has no spine info
    (malformed EPUB), to preserve indexing behavior on edge cases.
    """
    spine_docs = []
    spine = getattr(book, 'spine', None)
    if spine:
        for entry in spine:
            # book.spine entries are (idref, linear) tuples or bare idref strings.
            idref = entry[0] if isinstance(entry, (tuple, list)) else entry
            item = book.get_item_with_id(idref)
            if item is not None and item.get_type() == ebooklib.ITEM_DOCUMENT:
                spine_docs.append(item)
    if not spine_docs:
        # Malformed / spine-less EPUB — fall back to manifest order.
        spine_docs = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    return spine_docs


def _resolve_spine_labels(hrefs, href_to_label: dict) -> list:
    """Assign each spine item a label, carrying the most recently-matched TOC label
    forward so mid-chapter spine items inherit their chapter's label.

    `hrefs` is a list of (file_name, get_name) tuples in spine order. Items before
    the first TOC match (e.g. cover, title page) get a generic `Section N` fallback.
    """
    labels: list = []
    current_label = None
    for ordinal, (file_name, get_name) in enumerate(hrefs):
        new_label = href_to_label.get(file_name) or href_to_label.get(get_name)
        if new_label:
            current_label = new_label
        labels.append(current_label or f'Section {ordinal + 1}')
    return labels


def extract_epub(path: pathlib.Path) -> DocMetadata:
    """Extract metadata from an EPUB file using ebooklib."""
    if ebooklib is None or epub is None:
        raise ValueError('ebooklib is not installed')

    metadata = DocMetadata()

    try:
        book = epub.read_epub(path, options=dict(ignore_ncx=True))
    except Exception as e:
        logger.error(f'Failed to read epub {path}', exc_info=e)
        metadata.title = Indexer.get_title(path)
        return metadata

    for key, value in book.metadata.items():
        if 'title' in value:
            metadata.title = metadata.title or value['title'][0][0]
        if 'creator' in value:
            metadata.author = metadata.author or value['creator'][0][0]
        if 'publisher' in value:
            metadata.publisher = metadata.publisher or value['publisher'][0][0]
        if 'language' in value:
            metadata.language = metadata.language or value['language'][0][0]
        if 'description' in value:
            metadata.description = metadata.description or value['description'][0][0]
        if 'subject' in value:
            metadata.subject = metadata.subject or value['subject'][0][0]

    # Build a map of spine-item href -> chapter label from the TOC, if available.
    href_to_label = {}
    try:
        href_to_label = _build_epub_toc_label_map(book.toc)
    except Exception as e:
        logger.warning(f'Failed to walk EPUB TOC for {path}', exc_info=e)

    # Extract text per spine item, keeping a per-section record for deep-linking.
    # Many EPUBs (especially Calibre-converted ones) split chapters across many spine
    # items but only have a single TOC entry at the chapter start. Carry the most
    # recently-matched TOC label forward so mid-chapter sections still get a useful
    # label (e.g. "Mullein" rather than "Section 302").
    text_parts = []
    spine_items = _iter_epub_spine_documents(book)
    hrefs = [(d.file_name, d.get_name()) for d in spine_items]
    labels = _resolve_spine_labels(hrefs, href_to_label)
    for ordinal, (doc, label) in enumerate(zip(spine_items, labels)):
        section_text = _extract_text_from_html(doc.content)
        text_parts.append(section_text)
        capped = truncate_object_bytes(section_text, SECTION_MAX_TEXT_SIZE)
        metadata.sections.append(DocSection(
            kind='epub_spine',
            ordinal=ordinal,
            label=label,
            content=capped,
        ))
    metadata.text = ''.join(text_parts)

    # Extract cover.
    try:
        for doc in book.get_items_of_type(ebooklib.ITEM_COVER):
            metadata.cover_bytes = doc.content
            break
        if not metadata.cover_bytes:
            for doc in book.get_items_of_type(ebooklib.ITEM_IMAGE):
                metadata.cover_bytes = doc.content
                break
    except Exception as e:
        logger.warning(f'Failed to extract cover from {path}', exc_info=e)

    return metadata


def _parse_pdf_date(date_str: str):
    """Parse PDF date format 'D:YYYYMMDDHHmmSS+HH'mm'' to datetime."""
    if not date_str:
        return None
    try:
        parsed = dates.strpdate(date_str)
        if parsed and not parsed.tzinfo:
            parsed = parsed.astimezone(pytz.UTC)
        return parsed
    except Exception:
        return None


def extract_pdf(path: pathlib.Path) -> DocMetadata:
    """Extract metadata from a PDF using pymupdf."""
    if pymupdf is None:
        logger.error(f'Cannot extract PDF metadata: pymupdf is not installed')
        return DocMetadata(title=Indexer.get_title(path))

    metadata = DocMetadata()
    doc = None
    try:
        doc = pymupdf.open(path)

        pdf_meta = doc.metadata or {}
        if (title := pdf_meta.get('title')) and title.lower() != 'unknown':
            metadata.title = title
        if (author := pdf_meta.get('author')) and author.lower() != 'unknown':
            metadata.author = author
        if subject := pdf_meta.get('subject'):
            metadata.subject = subject

        metadata.page_count = doc.page_count

        if creation_date := pdf_meta.get('creationDate'):
            metadata.published_date = _parse_pdf_date(creation_date)

        # Extract text.
        if path.stat().st_size <= FILE_MAX_PDF_SIZE:
            try:
                words = []
                for page in doc:
                    text = page.get_text()
                    text = text.replace('\x00', '\uFFFD').strip()
                    if text:
                        words.append(text)
                        # Record a per-page section (1-based, matching the PDF viewer's
                        # `#page=N` fragment convention).
                        metadata.sections.append(DocSection(
                            kind='pdf_page',
                            ordinal=page.number + 1,
                            label=f'Page {page.number + 1}',
                            content=truncate_object_bytes(text, SECTION_MAX_TEXT_SIZE),
                        ))
                metadata.text = '\n'.join(
                    truncate_generator_bytes(iter(words), FILE_MAX_TEXT_SIZE))
            except Exception as e:
                logger.error(f'Failed to extract PDF text: {path}', exc_info=e)

        # Extract first page as cover thumbnail.
        try:
            if doc.page_count > 0:
                page = doc[0]
                pix = page.get_pixmap(matrix=pymupdf.Matrix(0.5, 0.5))
                metadata.cover_bytes = pix.tobytes('jpeg')
        except Exception as e:
            logger.warning(f'Failed to render PDF cover: {path}', exc_info=e)

    except Exception as e:
        logger.error(f'Failed to extract PDF metadata: {path}', exc_info=e)
        metadata.title = Indexer.get_title(path)
    finally:
        if doc:
            doc.close()

    return metadata


def extract_docx(path: pathlib.Path) -> DocMetadata:
    """Extract metadata from a DOCX file."""
    if docx is None:
        return DocMetadata(title=Indexer.get_title(path))

    metadata = DocMetadata()
    try:
        document = docx.Document(str(path))
        props = document.core_properties

        metadata.title = props.title or None
        metadata.author = props.author or None
        metadata.subject = props.subject or None
        metadata.description = props.comments or None
        metadata.language = props.language or None

        if props.created:
            metadata.published_date = props.created

        # Extract text.
        text_parts = []
        for para in document.paragraphs:
            if para.text:
                text_parts.append(para.text)
        metadata.text = truncate_object_bytes(' '.join(text_parts), FILE_MAX_TEXT_SIZE)
    except Exception as e:
        logger.error(f'Failed to extract docx metadata: {path}', exc_info=e)
        metadata.title = Indexer.get_title(path)

    return metadata


def extract_doc(path: pathlib.Path) -> DocMetadata:
    """Extract text from old .doc files using catdoc/textutil."""
    import subprocess
    from wrolpi.cmd import CATDOC_PATH, TEXTUTIL_PATH

    metadata = DocMetadata()
    metadata.title = Indexer.get_title(path)

    try:
        if CATDOC_PATH:
            cmd = (CATDOC_PATH, str(path.absolute()))
            proc = subprocess.run(cmd, capture_output=True)
            metadata.text = proc.stdout.decode()
        elif TEXTUTIL_PATH:
            cmd = (TEXTUTIL_PATH, '-stdout', '-cat', 'txt', str(path.absolute()))
            proc = subprocess.run(cmd, capture_output=True)
            metadata.text = proc.stdout.decode()

        if metadata.text:
            metadata.text = truncate_object_bytes(metadata.text, FILE_MAX_TEXT_SIZE)
    except Exception as e:
        logger.error(f'Failed to extract doc text: {path}', exc_info=e)

    return metadata


def extract_odt(path: pathlib.Path) -> DocMetadata:
    """Extract metadata from an ODT file by parsing meta.xml inside the zip."""
    metadata = DocMetadata()
    metadata.title = Indexer.get_title(path)

    try:
        with zipfile.ZipFile(path, 'r') as zf:
            if 'meta.xml' in zf.namelist():
                meta_xml = zf.read('meta.xml').decode('utf-8')
                import xml.etree.ElementTree as ET
                root = ET.fromstring(meta_xml)
                ns = {
                    'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
                    'dc': 'http://purl.org/dc/elements/1.1/',
                    'meta': 'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
                }
                office_meta = root.find('.//office:meta', ns)
                if office_meta is not None:
                    title_el = office_meta.find('dc:title', ns)
                    if title_el is not None and title_el.text:
                        metadata.title = title_el.text
                    creator_el = office_meta.find('dc:creator', ns)
                    if creator_el is not None and creator_el.text:
                        metadata.author = creator_el.text
                    subject_el = office_meta.find('dc:subject', ns)
                    if subject_el is not None and subject_el.text:
                        metadata.subject = subject_el.text
                    desc_el = office_meta.find('dc:description', ns)
                    if desc_el is not None and desc_el.text:
                        metadata.description = desc_el.text
                    lang_el = office_meta.find('dc:language', ns)
                    if lang_el is not None and lang_el.text:
                        metadata.language = lang_el.text

            # Extract text from content.xml.
            if 'content.xml' in zf.namelist():
                content_xml = zf.read('content.xml').decode('utf-8')
                import xml.etree.ElementTree as ET
                root = ET.fromstring(content_xml)
                # Get all text content.
                texts = []
                for elem in root.iter():
                    if elem.text:
                        texts.append(elem.text)
                    if elem.tail:
                        texts.append(elem.tail)
                metadata.text = truncate_object_bytes(' '.join(texts), FILE_MAX_TEXT_SIZE)
    except Exception as e:
        logger.error(f'Failed to extract ODT metadata: {path}', exc_info=e)

    return metadata


def _list_comic_archive(path: pathlib.Path):
    """Return (file_names, read_func) for a comic book archive.

    read_func(name) returns the bytes of the named member."""
    suffix = path.suffix.lower()
    if suffix in ('.cbz', '.zip'):
        zf = zipfile.ZipFile(path, 'r')
        return zf.namelist(), zf.read, zf
    elif suffix in ('.cbt',):
        import tarfile as _tarfile
        tf = _tarfile.open(path, 'r:*')
        names = [m.name for m in tf.getmembers() if not m.isdir()]

        def read_tar(name):
            f = tf.extractfile(name)
            return f.read() if f else b''

        return names, read_tar, tf
    elif suffix in ('.cbr',):
        import rarfile
        rf = rarfile.RarFile(path, 'r')
        return rf.namelist(), rf.read, rf
    elif suffix in ('.cb7',):
        import py7zr
        import tempfile
        sz = py7zr.SevenZipFile(path, 'r')
        tmpdir = tempfile.mkdtemp()
        sz.extractall(tmpdir)
        sz.close()
        names = []
        for root, dirs, files in os.walk(tmpdir):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), tmpdir)
                names.append(rel)

        def read_7z(name):
            return (pathlib.Path(tmpdir) / name).read_bytes()

        class Cleanup:
            def close(self):
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)

        return names, read_7z, Cleanup()
    return [], lambda n: b'', None


def extract_cbz(path: pathlib.Path) -> DocMetadata:
    """Extract metadata from comic book archives (CBZ, CBT, CBR, CB7)."""
    metadata = DocMetadata()
    metadata.title = Indexer.get_title(path)

    try:
        names, read_func, ctx = _list_comic_archive(path)
        try:
            # Look for ComicInfo.xml.
            for name in names:
                if name.lower().endswith('comicinfo.xml'):
                    try:
                        comic_xml = read_func(name).decode('utf-8')
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(comic_xml)
                        title_el = root.find('Title')
                        series_el = root.find('Series')
                        number_el = root.find('Number')
                        if series_el is not None and series_el.text:
                            # Use "Series #Number" as title if available.
                            title = series_el.text
                            if number_el is not None and number_el.text:
                                title = f'{title} #{number_el.text}'
                            metadata.title = title
                        elif title_el is not None and title_el.text:
                            metadata.title = title_el.text
                        writer_el = root.find('Writer')
                        if writer_el is not None and writer_el.text:
                            metadata.author = writer_el.text
                        summary_el = root.find('Summary')
                        if summary_el is not None and summary_el.text:
                            metadata.description = summary_el.text
                        page_count_el = root.find('PageCount')
                        if page_count_el is not None and page_count_el.text:
                            metadata.page_count = int(page_count_el.text)
                        publisher_el = root.find('Publisher')
                        if publisher_el is not None and publisher_el.text:
                            metadata.publisher = publisher_el.text
                        lang_el = root.find('LanguageISO')
                        if lang_el is not None and lang_el.text:
                            metadata.language = lang_el.text
                        genre_el = root.find('Genre')
                        if genre_el is not None and genre_el.text:
                            metadata.subject = genre_el.text
                        # Build published_date from Year/Month/Day.
                        year_el = root.find('Year')
                        if year_el is not None and year_el.text:
                            year = int(year_el.text)
                            month_el = root.find('Month')
                            day_el = root.find('Day')
                            month = int(month_el.text) if month_el is not None and month_el.text else 1
                            day = int(day_el.text) if day_el is not None and day_el.text else 1
                            metadata.published_date = datetime.datetime(year, month, day, tzinfo=pytz.UTC)
                    except Exception as e:
                        logger.warning(f'Failed to parse ComicInfo.xml: {path}', exc_info=e)
                    break

            # Extract first image as cover.
            image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
            image_names = sorted([n for n in names
                                  if any(n.lower().endswith(ext) for ext in image_extensions)])
            if image_names:
                metadata.cover_bytes = read_func(image_names[0])
        finally:
            if ctx:
                ctx.close()
    except Exception as e:
        logger.error(f'Failed to extract comic metadata: {path}', exc_info=e)

    return metadata
