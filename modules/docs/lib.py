import html
import logging
import pathlib
import re
from typing import List, Optional

from sqlalchemy import asc, desc, func, nullslast, text
from sqlalchemy.orm import Session

from wrolpi.collections.models import Collection
from wrolpi.collections.types import collection_type_registry
from wrolpi.db import get_db_session
from wrolpi.errors import ValidationError
from wrolpi.files.lib import split_path_stem_and_suffix, get_mimetype

logger = logging.getLogger(__name__)

# Register author and subject collection types.
collection_type_registry.register(
    'author',
    lambda n: bool(n and n.strip()),
    'Non-empty author name'
)

collection_type_registry.register(
    'subject',
    lambda n: bool(n and n.strip()),
    'Non-empty subject name'
)

# Junk author patterns to reject.
JUNK_AUTHORS = {
    'administrator', 'admin', 'unknown', 'preferred customer', 'user',
    'owner', 'default', 'none', 'n/a', 'na', 'test', 'root',
}

JUNK_SUBJECTS = {
    'unknown', 'n/a', 'na', 'none', 'test', 'default',
}

# Regex for URL-like strings.
URL_PATTERN = re.compile(r'https?://|www\.|\.com|\.org|\.net')

# Matches year ranges like 1483-1546, -1938, 1564-1616.
YEAR_RANGE_PATTERN = re.compile(r'^-?\d{0,4}-?\d{4}$')

# Matches bracket suffixes like [from old catalog].
BRACKET_SUFFIX_PATTERN = re.compile(r'\s*\]?\s*\[.*$')

# Matches trailing birth-death years like 1843-1920 at end of string.
TRAILING_YEARS_PATTERN = re.compile(r'\s+\d{4}-\d{4}$')

# Matches pure numeric/code patterns: 00110001, 062447, 105642-01, 01/2004.
NUMERIC_CODE_PATTERN = re.compile(r'^\d[\d\-/]*$')

# Matches date strings like "14 June 2006".
DATE_STRING_PATTERN = re.compile(r'^\d{1,2}\s+\w+\s+\d{4}$')

# Matches HTML entities like &bull; or &amp;
HTML_ENTITY_PATTERN = re.compile(r'&\w+;')

# Matches initials pattern like J.K. (used to avoid stripping trailing period).
INITIALS_PATTERN = re.compile(r'\.\w\.')


def normalize_author(author: str) -> Optional[str]:
    """Clean an author string before validation."""
    if not author or not author.strip():
        return None
    author = author.strip()

    # Remove bracket suffixes like [from old catalog].
    author = BRACKET_SUFFIX_PATTERN.sub('', author)

    # Strip surrounding quotes.
    if len(author) >= 2 and author[0] == '"' and author[-1] == '"':
        author = author[1:-1]
    # Also strip leading quote left after bracket removal.
    if author.startswith('"'):
        author = author[1:]

    # Remove surrounding parentheses.
    if len(author) >= 2 and author[0] == '(' and author[-1] == ')':
        author = author[1:-1]

    # Remove trailing birth-death years.
    author = TRAILING_YEARS_PATTERN.sub('', author)

    # Strip trailing period, but not if it's part of initials (e.g. J.K.).
    if author.endswith('.') and not INITIALS_PATTERN.search(author):
        author = author[:-1]

    # Strip trailing comma.
    author = author.rstrip(',')

    # Title-case for consistent casing.
    author = author.title()

    author = author.strip()
    return author if author else None


def normalize_subject(subject: str) -> Optional[str]:
    """Clean a subject string before validation."""
    if not subject or not subject.strip():
        return None
    subject = subject.strip()

    # Decode HTML entities.
    subject = html.unescape(subject)

    # Title-case for consistent casing.
    subject = subject.title()

    # Truncate to 150 chars.
    if len(subject) > 150:
        subject = subject[:150]

    subject = subject.strip()
    return subject if subject else None


# Matches pure digits.
PURE_DIGITS_PATTERN = re.compile(r'^\d+$')

# Matches any letter character.
HAS_LETTER_PATTERN = re.compile(r'[a-zA-Z]')


def is_valid_author(author: str) -> bool:
    """Check if an author string looks like a real author name."""
    if not author or not author.strip():
        return False
    author = author.strip()
    if len(author) > 100:
        return False
    if len(author) < 2:
        return False
    if author.lower() in JUNK_AUTHORS:
        return False
    if URL_PATTERN.search(author):
        return False
    # Reject pure year ranges and numbers.
    if YEAR_RANGE_PATTERN.match(author):
        return False
    if PURE_DIGITS_PATTERN.match(author):
        return False
    # Reject strings with no letter characters.
    if not HAS_LETTER_PATTERN.search(author):
        return False
    return True


def is_valid_subject(subject: str) -> bool:
    """Check if a subject string looks like a real subject."""
    if not subject or not subject.strip():
        return False
    subject = subject.strip()
    if len(subject) < 2:
        return False
    if len(subject) > 150:
        return False
    if subject.lower() in JUNK_SUBJECTS:
        return False
    if URL_PATTERN.search(subject):
        return False
    # Reject pure numeric/code patterns.
    if NUMERIC_CODE_PATTERN.match(subject):
        return False
    # Reject date strings.
    if DATE_STRING_PATTERN.match(subject):
        return False
    # Reject strings with HTML entities.
    if HTML_ENTITY_PATTERN.search(subject):
        return False
    return True


# Splits multiple authors on common separators.
AUTHOR_SPLIT_PATTERN = re.compile(r'[;&]|,\s*(?:and|&)\s*|,\s+')


def split_authors(author_str: str) -> List[str]:
    """Split an author string that may contain multiple authors."""
    if not author_str:
        return []
    # Split on common separators.
    authors = AUTHOR_SPLIT_PATTERN.split(author_str)
    return [a.strip() for a in authors if a.strip()]


# Splits multiple subjects on semicolons and bare commas.
SUBJECT_SPLIT_PATTERN = re.compile(r';|,(?!\s)')


def split_subjects(subject_str: str) -> List[str]:
    """Split a subject string that may contain multiple subjects."""
    if not subject_str:
        return []
    # Split on semicolons and bare commas (comma NOT followed by a space).
    subjects = SUBJECT_SPLIT_PATTERN.split(subject_str)
    return [s.strip() for s in subjects if s.strip()]


def get_or_create_author_collection(session: Session, author_name: str) -> Optional[Collection]:
    """Find or create a Collection for an author."""
    if not author_name or not author_name.strip():
        return None

    author_name = author_name.strip()
    collection = session.query(Collection).filter(
        func.lower(Collection.name) == author_name.lower(),
        Collection.kind == 'author',
    ).first()
    if not collection:
        collection = Collection(name=author_name, kind='author')
        session.add(collection)
        session.flush()
        logger.debug(f'Created author collection: {author_name}')
    return collection


def get_or_create_subject_collection(session: Session, subject_name: str) -> Optional[Collection]:
    """Find or create a Collection for a subject."""
    if not subject_name or not subject_name.strip():
        return None

    subject_name = subject_name.strip()
    collection = session.query(Collection).filter(
        func.lower(Collection.name) == subject_name.lower(),
        Collection.kind == 'subject',
    ).first()
    if not collection:
        collection = Collection(name=subject_name, kind='subject')
        session.add(collection)
        session.flush()
        logger.debug(f'Created subject collection: {subject_name}')
    return collection


async def search_authors_by_name(session: Session, name: str, limit: int = 5) -> List[dict]:
    """Search for author collections by partial name."""
    collections = session.query(Collection) \
        .filter(Collection.kind == 'author') \
        .filter(Collection.name.ilike(f'%{name}%')) \
        .order_by(asc(Collection.name)) \
        .limit(limit) \
        .all()
    return [{'id': c.id, 'name': c.name} for c in collections]


async def search_subjects_by_name(session: Session, name: str, limit: int = 5) -> List[dict]:
    """Search for subject collections by partial name."""
    collections = session.query(Collection) \
        .filter(Collection.kind == 'subject') \
        .filter(Collection.name.ilike(f'%{name}%')) \
        .order_by(asc(Collection.name)) \
        .limit(limit) \
        .all()
    return [{'id': c.id, 'name': c.name} for c in collections]


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


def get_statistics() -> dict:
    """Get doc statistics."""
    from .models import Doc
    from wrolpi.files.models import FileGroup

    with get_db_session() as session:
        total = session.query(func.count(Doc.id)).scalar() or 0
        total_size = session.query(func.sum(Doc.size)).scalar() or 0

        epub_count = session.query(func.count(Doc.id)).join(FileGroup).filter(
            FileGroup.mimetype.startswith('application/epub')).scalar() or 0
        pdf_count = session.query(func.count(Doc.id)).join(FileGroup).filter(
            FileGroup.mimetype == 'application/pdf').scalar() or 0

        author_count = session.query(func.count(Collection.id)).filter(
            Collection.kind == 'author').scalar() or 0
        subject_count = session.query(func.count(Collection.id)).filter(
            Collection.kind == 'subject').scalar() or 0

    return dict(statistics=dict(
        doc_count=total,
        epub_count=epub_count,
        pdf_count=pdf_count,
        other_count=total - epub_count - pdf_count,
        total_size=total_size,
        author_count=author_count,
        subject_count=subject_count,
    ))


def _doc_response(doc) -> dict:
    """Build a JSON response dict for a Doc."""
    file_group = doc.file_group.__json__()
    return {
        'file_group': file_group,
        'doc': {
            'id': doc.id,
            'publisher': doc.publisher,
            'language': doc.language,
            'page_count': doc.page_count,
            'subject': doc.subject,
            'description': doc.description,
            'size': doc.size,
        }
    }


def _get_doc(session, file_group_id: int):
    from .models import Doc
    doc = session.query(Doc).filter_by(file_group_id=file_group_id).one_or_none()
    if not doc:
        raise ValidationError(f'Doc with file_group_id {file_group_id} not found')
    return doc


def _delete_docs(*file_group_ids):
    from .models import Doc
    with get_db_session(commit=True) as session:
        for file_group_id in file_group_ids:
            doc = session.query(Doc).filter_by(file_group_id=file_group_id).one_or_none()
            if doc:
                session.delete(doc)


def _search_docs(search_str=None, author=None, subject=None, language=None, mimetype=None,
                 limit=20, offset=0, order_by='published_datetime', tag_names=None):
    from .models import Doc
    from wrolpi.files.models import FileGroup

    with get_db_session() as session:
        query = session.query(FileGroup).join(Doc, Doc.file_group_id == FileGroup.id)

        if search_str:
            query = query.filter(FileGroup.textsearch.op('@@')(func.websearch_to_tsquery(search_str)))

        if author:
            query = query.filter(FileGroup.b_text.ilike(f'%{author}%'))

        if subject:
            query = query.filter(Doc.subject.ilike(f'%{subject}%'))

        if language:
            query = query.filter(Doc.language == language)

        if mimetype:
            query = query.filter(FileGroup.mimetype.startswith(mimetype))

        if tag_names:
            from wrolpi.tags import Tag, TagFile
            tagged_fg_ids = session.query(TagFile.file_group_id) \
                .join(Tag, Tag.id == TagFile.tag_id) \
                .filter(Tag.name.in_(tag_names)) \
                .subquery()
            query = query.filter(FileGroup.id.in_(tagged_fg_ids))

        total = query.count()

        # Ordering.
        if order_by == 'rank' and search_str:
            query = query.order_by(
                desc(func.ts_rank(FileGroup.textsearch, func.websearch_to_tsquery(search_str))),
                desc(FileGroup.id),
            )
        elif order_by == 'published_datetime':
            query = query.order_by(nullslast(desc(FileGroup.published_datetime)), desc(FileGroup.id))
        elif order_by == 'size':
            query = query.order_by(nullslast(desc(Doc.size)))
        elif order_by == 'title':
            query = query.order_by(nullslast(asc(FileGroup.a_text)))
        else:
            query = query.order_by(desc(FileGroup.id))

        file_groups = query.offset(offset).limit(limit).all()
        fg_ids = [fg.id for fg in file_groups]
        results = [fg.__json__() for fg in file_groups]

        if search_str and fg_ids:
            hints = _fetch_section_hints(session, fg_ids, search_str)
            for r in results:
                hint = hints.get(r['id'])
                if hint:
                    r['section_hint'] = hint

    return results, total


def _fetch_section_hints(session, file_group_ids, search_str):
    """For each matching Doc, return the best-ranking DocSection for `search_str`.

    Returns a mapping of file_group_id -> {kind, ordinal, label, snippet}.
    """
    from .models import Doc, DocSection

    if not file_group_ids:
        return {}

    sql = text('''
        SELECT DISTINCT ON (d.file_group_id)
            d.file_group_id AS fg_id,
            ds.kind AS kind,
            ds.ordinal AS ordinal,
            ds.label AS label,
            ts_headline('english', ds.content, q,
                        'MaxWords=20,MinWords=5,ShortWord=3,StartSel=[[WROLPI_HL]],StopSel=[[/WROLPI_HL]]') AS snippet
        FROM doc_section ds
        JOIN doc d ON d.id = ds.doc_id,
             websearch_to_tsquery('english', :q) q
        WHERE d.file_group_id = ANY(:ids) AND ds.tsv @@ q
        ORDER BY d.file_group_id, ts_rank(ds.tsv, q) DESC, ds.ordinal ASC
    ''')
    rows = session.execute(sql, {'q': search_str, 'ids': list(file_group_ids)}).fetchall()
    hints = {}
    for row in rows:
        hints[row['fg_id']] = {
            'kind': row['kind'],
            'ordinal': row['ordinal'],
            'label': row['label'],
            'snippet': row['snippet'],
        }
    return hints
