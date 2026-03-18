import pathlib
from typing import Optional

from sqlalchemy import Column, Integer, BigInteger, ForeignKey, String, Text, Index, or_
from sqlalchemy.orm import relationship, Session

from wrolpi.common import ModelHelper, Base
from wrolpi.db import get_db_session
from wrolpi.files.models import FileGroup

EPUB_MIMETYPE = 'application/epub'
MOBI_MIMETYPE = 'application/x-mobipocket-ebook'

DOC_MIMETYPES = (
    'application/epub+zip',
    'application/x-mobipocket-ebook',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.oasis.opendocument.text',
    'application/vnd.comicbook-rar',
    'application/vnd.comicbook+zip',
    'application/x-cbz',
    'application/x-cbr',
    'application/x-cbt',
    'application/x-cb7',
)

# Mimetypes that are considered ebook formats.
EBOOK_MIMETYPES = (
    EPUB_MIMETYPE,
    MOBI_MIMETYPE,
)


COMIC_BOOK_SUFFIXES = ('.cbz', '.cbr', '.cbt', '.cb7')


def mimetype_is_doc(mimetype: str) -> bool:
    """Check if a mimetype is a doc type that the Doc model handles."""
    return any(mimetype.startswith(mt) for mt in DOC_MIMETYPES)


class Doc(ModelHelper, Base):
    __tablename__ = 'doc'
    __table_args__ = (
        Index('doc_size_idx', 'size'),
    )

    id = Column(Integer, primary_key=True)
    size = Column(BigInteger)
    publisher = Column(String)
    language = Column(String)
    page_count = Column(Integer)
    subject = Column(String)
    description = Column(Text)

    file_group_id = Column(BigInteger, ForeignKey('file_group.id', ondelete='CASCADE'), nullable=False, unique=True)
    file_group: FileGroup = relationship('FileGroup')

    def __repr__(self):
        path = str(self.file_group.primary_path) if self.file_group else 'None'
        return f'<Doc id={self.id} path={repr(path)} file_group_id={self.file_group_id}>'

    def __json__(self) -> dict:
        d = self.file_group.__json__()
        if d.get('data') and d['data'].get('doc_path'):
            d['data']['doc_path'] = self.file_group.resolve_path(d['data']['doc_path'])
        if d.get('data') and d['data'].get('cover_path'):
            d['data']['cover_path'] = self.file_group.resolve_path(d['data']['cover_path'])
        # Also handle legacy ebook_path key.
        if d.get('data') and d['data'].get('ebook_path'):
            d['data']['ebook_path'] = self.file_group.resolve_path(d['data']['ebook_path'])
        return d

    @staticmethod
    def can_model(file_group: FileGroup) -> bool:
        if file_group.mimetype and mimetype_is_doc(file_group.mimetype):
            return True
        if file_group.primary_path and file_group.primary_path.suffix.lower() in COMIC_BOOK_SUFFIXES:
            return True
        return False

    @staticmethod
    def do_model(session: Session, file_group: FileGroup) -> 'Doc':
        from modules.docs import _model_doc
        doc = _model_doc(file_group, session)
        file_group.model = Doc.__tablename__
        file_group.indexed = True
        return doc

    @property
    def cover_file(self) -> Optional[dict]:
        posters = self.file_group.my_poster_files()
        if posters:
            return posters[0]
        return None

    @property
    def cover_path(self) -> Optional[pathlib.Path]:
        cover = self.cover_file
        if cover:
            return cover['path']
        return None

    def _hide_calibre_files(self, file_group: FileGroup):
        """Delete FileGroups of the cover/metadata when this is a Calibre ebook directory."""
        from modules.docs.lib import discover_calibre_cover
        path = file_group.primary_path
        if not discover_calibre_cover(path):
            raise ValueError(f'Refusing to hide Calibre files when we do not have a Calibre ebook directory!')

        metadata = path.parent / 'metadata.opf'
        cover = path.parent / 'cover.jpg'

        with get_db_session(commit=True) as session:
            file_groups = session.query(FileGroup).filter(or_(
                FileGroup.primary_path == str(metadata),
                FileGroup.primary_path == str(cover),
            ))
            for fg in file_groups:
                session.delete(fg)
