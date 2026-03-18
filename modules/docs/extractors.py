import dataclasses
import datetime
import logging
import os
import pathlib
import zipfile

import pytz

from wrolpi import dates
from wrolpi.common import truncate_generator_bytes, truncate_object_bytes, get_html_soup
from wrolpi.files.indexers import Indexer
from wrolpi.files.models import FileGroup
from wrolpi.vars import FILE_MAX_PDF_SIZE, FILE_MAX_TEXT_SIZE

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

    # Extract text.
    text_parts = []
    for doc in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        text_parts.append(_extract_text_from_html(doc.content))
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
