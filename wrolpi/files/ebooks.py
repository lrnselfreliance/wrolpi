import asyncio
import dataclasses
import logging
import pathlib
from typing import List, Optional, Tuple

from sqlalchemy import Column, Integer, BigInteger, ForeignKey, or_, and_
from sqlalchemy.orm import relationship, Session

from wrolpi.common import ModelHelper, Base, register_modeler, get_html_soup
from wrolpi.db import get_db_session
from wrolpi.files.lib import split_path_stem_and_suffix, get_mimetype
from wrolpi.files.models import FileGroup
from wrolpi.vars import PYTEST

try:
    import ebooklib
    from ebooklib import epub
except ImportError:
    ebooklib = None
    epub = None

logger = logging.getLogger(__name__)

__all__ = [
    'EBOOK_MIMETYPES',
    'EBook',
    'EBookData',
    'EPUB_MIMETYPE',
    'MOBI_MIMETYPE',
    'ebook_modeler',
    'extract_ebook_cover',
    'extract_ebook_data',
    'mimetype_is_ebook',
    'model_ebook',
]

EBOOK_SUFFIXES = ('.epub', '.mobi')
EPUB_MIMETYPE = 'application/epub'
MOBI_MIMETYPE = 'application/x-mobipocket-ebook'

EBOOK_MIMETYPES = (
    EPUB_MIMETYPE,
    MOBI_MIMETYPE,
)


@dataclasses.dataclass
class EBookData:
    cover: bytes = None
    author: str = None
    text: str = None
    title: str = None
    ebook_path: pathlib.Path = None

    def __bool__(self):
        return bool(self.cover) or bool(self.author) or bool(self.text) or bool(self.title)

    def __json__(self) -> dict:
        d = {}
        if self.author:
            d['author'] = self.author
        if self.title:
            d['title'] = self.title
        if self.ebook_path:
            d['ebook_path'] = self.ebook_path
        return d


def extract_text(html: str) -> str:
    soup = get_html_soup(html)
    text = soup.get_text()
    return text


def mimetype_is_ebook(mimetype: str) -> bool:
    return any(i for i in EBOOK_MIMETYPES if mimetype.startswith(i))


def extract_ebook_data(path: pathlib.Path, mimetype: str) -> Optional[EBookData]:
    """Extract data from within an eBook file."""
    if ebooklib is None or epub is None:
        raise ValueError('ebooklib is not installed')
    if not mimetype.startswith(EPUB_MIMETYPE):
        return None

    data = EBookData(ebook_path=path)

    book = epub.read_epub(path, options=dict(ignore_ncx=True))
    for key, value in book.metadata.items():
        if 'title' in value:
            data.title = data.title or value['title'][0][0]
        if 'creator' in value:
            data.author = data.author or value['creator'][0][0]

    data.text = ''
    for doc in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        data.text += extract_text(doc.content)

    return data


def extract_ebook_cover(path: pathlib.Path) -> Optional[bytes]:
    """Attempt to find the Cover within an ePub file.  If no cover is found, return the first image."""
    if ebooklib is None or epub is None:
        raise ValueError('ebooklib is not installed')

    book = epub.read_epub(path, options=dict(ignore_ncx=True))

    for doc in book.get_items_of_type(ebooklib.ITEM_COVER):
        logger.debug(f'Found cover for {path}')
        return doc.content

    # Use the first image as the cover.
    for doc in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        logger.debug(f'Using first image as cover for {path}')
        return doc.content


def discover_calibre_cover(ebook_path: pathlib.Path):
    """Calibre puts a cover file in a directory which contains only one ebook (but multiple formats of the ebook),
    this function will return the path of the cover if the ebook_path is in such a situation."""
    if not ebook_path.is_file():
        raise ValueError(f'Invalid ebook path {ebook_path}')

    paths = list(ebook_path.parent.iterdir())

    ebook_path_stem, _ = split_path_stem_and_suffix(ebook_path)

    cover = None
    for path in paths:
        stem, suffix = split_path_stem_and_suffix(path)
        if path.is_dir():
            # We don't care about sub directories.
            continue
        if stem == ebook_path_stem:
            # This is one of the formats of the ebook.
            continue
        if path.name == 'metadata.opf':
            # Metadata, this is expected in a Calibre book directory.
            continue
        if stem == 'cover' and get_mimetype(path).startswith('image/'):
            # Discovered the cover.
            cover = path
            continue
        # Some file that does not match the ebook stem, metadata, or cover.  This must not be a Calibre book directory.
        return None
    return cover


class EBook(ModelHelper, Base):
    __tablename__ = 'ebook'
    id = Column(Integer, primary_key=True)
    size: int = Column(Integer)

    file_group_id = Column(BigInteger, ForeignKey('file_group.id', ondelete='CASCADE'), nullable=False, unique=True)
    file_group: FileGroup = relationship('FileGroup')

    def __repr__(self):
        path = str(self.file_group.primary_path)
        return f'<EBook id={self.id} path={repr(path)} file_group_id={self.file_group_id}>'

    def __json__(self) -> dict:
        # Convert this eBook's paths to pathlib.Paths.
        d = self.file_group.__json__()
        d['data']['ebook_path'] = pathlib.Path(d['data']['ebook_path'])
        d['data']['cover_path'] = pathlib.Path(d['data']['cover_path']) if 'cover_path' in d['data'] else None
        return d

    @staticmethod
    def can_model(file_group: FileGroup) -> bool:
        if mimetype_is_ebook(file_group.mimetype):
            return True
        return False

    @staticmethod
    def do_model(file_group: FileGroup, session: Session) -> 'EBook':
        ebook = model_ebook(file_group, session)
        file_group.indexed = True
        return ebook

    def generate_cover(self) -> Optional[pathlib.Path]:
        """Discover this ebook's cover, if found, store it next to the ebook file."""
        path = self.file_group.primary_path

        if not path:
            raise ValueError('Cannot generate cover for ebook without ebook file!')

        if calibre_cover := discover_calibre_cover(path):
            self.hide_calibre_files()
            return calibre_cover

        cover_bytes = extract_ebook_cover(path)
        if cover_bytes:
            cover_path = path.with_suffix('.jpeg')
            cover_path.write_bytes(cover_bytes)
            return cover_path

        logger.warning(f'Unable to generate ebook cover for {self.file_group.primary_path}')

    @property
    def cover_file(self) -> Optional[dict]:
        posters = self.file_group.my_poster_files()
        return posters[0]

    @property
    def cover_path(self) -> Optional[pathlib.Path]:
        return self.cover_file['path']

    def hide_calibre_files(self):
        """Delete FileGroups of the cover/metadata when this is a Calibre ebook directory."""
        path = self.file_group.primary_path
        if not discover_calibre_cover(path):
            raise ValueError(f'Refusing to hide Calibre files when we do not have a Calibre ebook directory!')

        metadata = path.parent / 'metadata.opf'
        cover = path.parent / 'cover.jpg'

        with get_db_session(commit=True) as session:
            file_groups = session.query(FileGroup) \
                .filter(or_(
                FileGroup.primary_path == str(metadata),
                FileGroup.primary_path == str(cover),
            ))
            for file_group in file_groups:
                session.delete(file_group)


def model_ebook(file_group: FileGroup, session: Session) -> EBook:
    """Creates an EBook model based off a File.  Searches for its cover in the provided `files`."""
    ebook = EBook(file_group=file_group)
    session.add(ebook)

    # Multiple formats may be available.
    epub_file = next(iter(ebook.file_group.my_epub_files()), None)
    mobi_file = next(iter(ebook.file_group.my_mobi_files()), None)
    # epub is preferred because it can be indexed.
    if epub_file:
        ebook_file = epub_file['path']
        ebook_mimetype = epub_file['mimetype']
    elif mobi_file:
        ebook_file = mobi_file['path']
        ebook_mimetype = mobi_file['mimetype']
    else:
        raise ValueError(f'No epub or mobi found.  {ebook}')

    size = ebook_file.stat().st_size

    # Only index if it hasn't been done, or if the file has changed.
    changed = size != ebook.size or not ebook.file_group.title
    if epub_file and changed:
        # Only read the contents of the file if it has changed.
        try:
            data = extract_ebook_data(ebook_file, ebook_mimetype)
            if data:
                # Title is a_text.
                ebook.file_group.title = ebook.file_group.a_text = data.title
                # Author is b_text.
                ebook.file_group.b_text = ebook.file_group.author = data.author
                # All text is d_text.
                ebook.file_group.d_text = data.text
                d: dict = data.__json__()
                d['ebook_path'] = str(d['ebook_path'])
                ebook.file_group.data = d
        except Exception as e:
            logger.error(f'Failed to extract epub book data', exc_info=e)

        if ebook.file_group.my_poster_files():
            ebook.file_group.data['cover_path'] = ebook.file_group.my_poster_files()[0]['path']
        else:
            # Extract cover because there is no cover file.
            cover_path = ebook.generate_cover()
            if cover_path:
                ebook.file_group.append_files(cover_path)
                ebook.file_group.data['cover_path'] = str(cover_path)

    if not ebook.file_group.title:
        # Book was not indexed above (probably a MOBI), use the file data.
        stem, _ = split_path_stem_and_suffix(ebook.file_group.primary_path)
        ebook.file_group.title = stem

    ebook.size = size
    ebook.flush()

    return ebook


def find_ebook_files_in_group(group: List):
    """Returns a list of any File records if they are an ebook."""
    return list(filter(lambda i: mimetype_is_ebook(i.mimetype), group))


@register_modeler
async def ebook_modeler():
    """Searches for ebook files and models them into the ebook table."""
    while True:
        with get_db_session(commit=True) as session:
            file_groups = session.query(FileGroup, EBook).filter(
                or_(
                    FileGroup.mimetype == 'application/epub+zip',
                    FileGroup.mimetype == 'application/x-mobipocket-ebook',
                ),
                FileGroup.indexed == False,
            ).outerjoin(EBook, and_(EBook.file_group_id == FileGroup.id)) \
                .limit(10)
            file_groups: List[Tuple[FileGroup, EBook]] = list(file_groups)

            processed = 0
            for file_group, ebook in file_groups:
                processed += 1
                try:
                    if PYTEST:
                        # Handle caching issue during testing.
                        session.expire(file_group)
                    ebook = ebook or model_ebook(file_group, session)
                    session.add(ebook)
                    file_group.model = EBook.__tablename__
                    file_group.indexed = True
                except Exception as e:
                    logger.error(f'Failed to index ebook {file_group}', exc_info=e)
                    if PYTEST:
                        raise

            session.commit()

            if processed < 10:
                # Did not reach limit, no more books.
                break

        # Sleep to catch cancel.
        await asyncio.sleep(0)
