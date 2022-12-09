import dataclasses
import logging
import pathlib
from typing import Dict, List, Generator, Optional

import bs4
from sqlalchemy import Column, Integer, ForeignKey, String
from sqlalchemy.orm import Session, relationship

from wrolpi.common import register_modeler, ModelHelper, Base, register_after_refresh
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.files.lib import split_path_stem_and_suffix, get_mimetype
from wrolpi.files.models import File
from wrolpi.media_path import MediaPathType

try:
    import ebooklib
    from ebooklib import epub
except ImportError:
    ebooklib = None
    epub = None

logger = logging.getLogger(__name__)

__all__ = [
    'EBook',
    'EBookData',
    'extract_ebook_cover',
    'extract_ebook_data',
    'ebook_modeler',
    'MOBI_MIMETYPE',
    'EPUB_MIMETYPE'
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
    creator: str = None
    text: str = None
    title: str = None

    def __bool__(self):
        return bool(self.cover) or bool(self.creator) or bool(self.text) or bool(self.title)


def extract_text(html: str) -> str:
    soup = bs4.BeautifulSoup(html, features='html.parser')
    text = soup.get_text()
    return text


def mimetype_is_ebook(mimetype: str) -> bool:
    return any(mimetype.startswith(i) for i in EBOOK_MIMETYPES)


def extract_ebook_data(path: pathlib.Path, mimetype: str) -> Optional[EBookData]:
    """Extract data from within an eBook file."""
    if ebooklib is None or epub is None:
        raise ValueError('ebooklib is not installed')
    if not mimetype.startswith(EPUB_MIMETYPE):
        return None

    data = EBookData()

    book = epub.read_epub(path, options=dict(ignore_ncx=True))
    for key, value in book.metadata.items():
        if 'title' in value:
            data.title = data.title or value['title'][0][0]
        if 'creator' in value:
            data.creator = data.creator or value['creator'][0][0]

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

    title: str = Column(String)
    creator: str = Column(String)

    ebook_path: pathlib.Path = Column(MediaPathType, ForeignKey('file.path', ondelete='CASCADE'))
    ebook_file: File = relationship('File', primaryjoin='EBook.ebook_path==File.path')
    cover_path: pathlib.Path = Column(MediaPathType, ForeignKey('file.path', ondelete='CASCADE'))
    cover_file: File = relationship('File', primaryjoin='EBook.cover_path==File.path')

    def __repr__(self):
        cover = 'yes' if self.cover_file else 'no'
        return f'<EBook id={self.id} path={repr(self.ebook_path)} cover={cover}>'

    def my_paths(self) -> Generator[pathlib.Path, None, None]:
        if self.ebook_path:
            yield self.ebook_path
        if self.cover_path:
            yield self.cover_path

    def my_files(self) -> Generator[File, None, None]:
        if self.ebook_file:
            yield self.ebook_file
        if self.cover_file:
            yield self.cover_file

    def __json__(self):
        d = dict(
            cover_path=self.cover_path,
            creator=self.creator,
            ebook_path=self.ebook_path,
            id=self.id,
            size=self.size,
            title=self.title,
        )
        return d

    def generate_cover(self) -> Optional[pathlib.Path]:
        """Discover this ebook's cover, if found, store it next to the ebook file."""
        path = self.ebook_file.path if self.ebook_file else self.ebook_path

        if not path:
            raise ValueError('Cannot generate cover for ebook without ebook file!')

        if calibre_cover := discover_calibre_cover(path):
            return calibre_cover

        cover_bytes = extract_ebook_cover(path)
        if cover_bytes:
            cover_path = path.with_suffix('.jpeg')
            cover_path.write_bytes(cover_bytes)
            return cover_path

        logger.warning(f'Unable to generate cover for {self.ebook_path}')

    @staticmethod
    def find_by_path(path, session) -> Base:
        return session.query(EBook).filter(EBook.ebook_path == path).one_or_none()


def model_ebook(session: Session, ebook_file: File, files: List[File]) -> EBook:
    """
    Creates an EBook model based off a File.  Searches for it's cover in the provided `files`.
    """
    # Multiple formats may share this cover.
    cover_file = next((i for i in files if i.mimetype.split('/')[0] == 'image'), None)

    ebook = session.query(EBook).filter_by(ebook_file=ebook_file).one_or_none()
    if not ebook:
        ebook = EBook(ebook_file=ebook_file)
        session.add(ebook)

    size = ebook_file.path.stat().st_size

    ebook.ebook_file.do_index()

    index = size != ebook.size or cover_file != ebook.cover_file or not ebook.title
    if not ebook.ebook_file.indexed or index:
        try:
            # Only read the contents of the file if it has changed.
            data = extract_ebook_data(ebook_file.path, ebook_file.mimetype)
            if data:
                # Title is a_text.
                ebook.ebook_file.a_text = ebook.title = data.title
                # Creator is b_text.
                ebook.ebook_file.b_text = ebook.creator = data.creator
                # All text is d_text.
                ebook.ebook_file.d_text = data.text
        except Exception as e:
            logger.error(f'Failed to extract book data', exc_info=e)

    if not ebook.title:
        # Book was not indexed above (probably a MOBI), use the file data.
        name, _ = split_path_stem_and_suffix(ebook.ebook_file.path)
        ebook.title = ebook.ebook_file.a_text = name

    if cover_file:
        cover_file.associated = True

    ebook.cover_file = cover_file
    ebook.size = size
    ebook_file.model = EBook.__tablename__

    return ebook


@register_modeler
def ebook_modeler(groups: Dict[str, List[File]], session: Session):
    """Searches for ebook files and models them into the ebook table.

    May generate cover files for EPUBs."""
    local_groups = groups.copy()

    for stem, group in local_groups.items():
        found_ebook = False
        for file in group:
            if not mimetype_is_ebook(file.mimetype):
                continue

            session.flush(group)
            model_ebook(session, file, group)

            found_ebook = True

        if found_ebook:
            # Claim this group for this ebook.
            del groups[stem]


@register_after_refresh
def discover_ebook_covers():
    """Discovers/extracts ebook covers for any Ebook that is missing one."""
    with get_db_curs() as curs:
        stmt = f'''
            SELECT e.id
            FROM ebook e
            LEFT JOIN file f on e.ebook_path = f.path
            WHERE
                e.cover_path IS NULL
                AND f.mimetype LIKE '{EPUB_MIMETYPE}%' '''
        curs.execute(stmt)
        missing_covers = [i[0] for i in curs.fetchall()]

    if not missing_covers:
        logger.info('No ebook covers to generate')
        return

    logger.warning(f'Discovering/generating {len(missing_covers)} ebook covers')

    for id_ in missing_covers:
        with get_db_session(commit=True) as session:
            ebook: EBook = session.query(EBook).filter(EBook.id == id_).one()

            cover_path = ebook.generate_cover()
            if cover_path:
                # Cover was generated or discovered.  Associate it with the ebook.
                cover_file = session.query(File).filter(File.path == cover_path).one_or_none()
                if not cover_file:
                    cover_file = File(path=cover_path)
                    session.add(cover_file)
                cover_file.do_index()
                cover_file.associated = True

                ebook.cover_file = cover_file
