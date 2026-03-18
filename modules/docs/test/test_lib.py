import pytest

from modules.docs.lib import is_valid_author, split_authors, get_or_create_author_collection, \
    get_or_create_subject_collection, normalize_author, normalize_subject, split_subjects, is_valid_subject, \
    search_authors_by_name, search_subjects_by_name


def test_is_valid_author():
    """Author validation rejects junk values."""
    assert is_valid_author('John Smith')
    assert is_valid_author('J.K. Rowling')
    assert is_valid_author('Dr. Seuss')

    # Reject junk.
    assert not is_valid_author('')
    assert not is_valid_author(None)
    assert not is_valid_author('Administrator')
    assert not is_valid_author('administrator')
    assert not is_valid_author('Preferred Customer')
    assert not is_valid_author('Unknown')
    assert not is_valid_author('www.example.com')
    assert not is_valid_author('https://example.com')
    assert not is_valid_author('A')  # Too short.
    assert not is_valid_author('x' * 101)  # Too long.

    # Reject year ranges and pure numbers.
    assert not is_valid_author('1483-1546')
    assert not is_valid_author('1564-1616')
    assert not is_valid_author('-1938')
    assert not is_valid_author('1851-1915')
    assert not is_valid_author('1114690')
    assert not is_valid_author('1588-1679')

    # Reject strings with no letters.
    assert not is_valid_author('12345')
    assert not is_valid_author('---')


def test_split_authors():
    """Author strings with multiple authors are split correctly."""
    assert split_authors('John Smith') == ['John Smith']
    assert split_authors('John Smith; Jane Doe') == ['John Smith', 'Jane Doe']
    assert split_authors('John Smith & Jane Doe') == ['John Smith', 'Jane Doe']
    assert split_authors('') == []
    assert split_authors(None) == []


def test_normalize_author():
    """Author names are cleaned up before validation."""
    # Strip surrounding quotes.
    assert normalize_author('"Tony R. Kuphaldt"') == 'Tony R. Kuphaldt'
    assert normalize_author('"Mrs. D.A. Lincoln"') == 'Mrs. D.A. Lincoln'

    # Remove bracket suffixes.
    assert normalize_author('"Mrs. A. J. Barnes." [from old catalog]') == 'Mrs. A. J. Barnes'
    assert normalize_author('Catherine] [from old catalog]') == 'Catherine'
    assert normalize_author('1851-1915. [from old catalog]') == '1851-1915'
    assert normalize_author('"Mrs. John Sterling," [from old catalog] ed') == 'Mrs. John Sterling'

    # Remove trailing birth-death years.
    assert normalize_author('Caroline Althea (Stickney) 1843-1920') == 'Caroline Althea (Stickney)'
    assert normalize_author('1851-1917') == '1851-1917'  # All numeric, nothing to strip — normalization passes through.

    # Strip trailing period (but not initials).
    assert normalize_author('Carol Ann.') == 'Carol Ann'
    assert normalize_author('J.K.') == 'J.K.'  # Initials stay.
    assert normalize_author('Dr. Seuss') == 'Dr. Seuss'  # Mid-string period stays.

    # Surrounding parentheses.
    assert normalize_author('(Thomas Joseph Workman)') == 'Thomas Joseph Workman'
    assert normalize_author('(Roland)') == 'Roland'

    # Title-case normalization.
    assert normalize_author('john smith') == 'John Smith'
    assert normalize_author('JOHN SMITH') == 'John Smith'
    assert normalize_author('John Smith') == 'John Smith'
    assert normalize_author('j.k. rowling') == 'J.K. Rowling'

    # Empty/None.
    assert normalize_author('') is None
    assert normalize_author(None) is None
    assert normalize_author('   ') is None


def test_is_valid_subject():
    """Subject validation rejects junk values."""
    # Valid subjects.
    assert is_valid_subject('Farming')
    assert is_valid_subject('Computer Science')
    assert is_valid_subject('First Aid')
    assert is_valid_subject('Science, Technology and Society')

    # Reject empty/short/long.
    assert not is_valid_subject('')
    assert not is_valid_subject(None)
    assert not is_valid_subject('A')
    assert not is_valid_subject('x' * 151)

    # Reject pure numeric/codes.
    assert not is_valid_subject('00110001')
    assert not is_valid_subject('062447')
    assert not is_valid_subject('105642-01')
    assert not is_valid_subject('106763-01')

    # Reject date-like strings.
    assert not is_valid_subject('01/2004')
    assert not is_valid_subject('04/2005')
    assert not is_valid_subject('14 June 2006')

    # Reject HTML entities.
    assert not is_valid_subject('something &bull; else')

    # Reject URLs.
    assert not is_valid_subject('https://example.com')
    assert not is_valid_subject('www.example.com')

    # Reject junk names.
    assert not is_valid_subject('unknown')
    assert not is_valid_subject('n/a')


def test_normalize_subject():
    """Subject strings are cleaned up before validation."""
    # Strip whitespace.
    assert normalize_subject('  Farming  ') == 'Farming'

    # Decode HTML entities.
    assert normalize_subject('First &amp; Second') == 'First & Second'

    # Truncate long strings.
    long_subject = 'x' * 200
    assert len(normalize_subject(long_subject)) == 150

    # Title-case normalization.
    assert normalize_subject('science fiction') == 'Science Fiction'
    assert normalize_subject('SCIENCE FICTION') == 'Science Fiction'
    assert normalize_subject('fairy tales') == 'Fairy Tales'
    assert normalize_subject('Fairy Tales') == 'Fairy Tales'

    # Empty/None.
    assert normalize_subject('') is None
    assert normalize_subject(None) is None
    assert normalize_subject('   ') is None


def test_split_subjects():
    """Subject strings with multiple subjects are split correctly."""
    # Split on bare commas (no trailing space).
    assert split_subjects('First Aid,GENERAL PREP.,HEALTH') == ['First Aid', 'GENERAL PREP.', 'HEALTH']

    # Split on semicolons.
    assert split_subjects('Science; Technology') == ['Science', 'Technology']

    # Preserve commas followed by space (legitimate compound subjects).
    assert split_subjects('Science, Technology and Society') == ['Science, Technology and Society']

    # Empty/None.
    assert split_subjects('') == []
    assert split_subjects(None) == []


def test_get_or_create_author_collection(test_session):
    """Author collections are created and reused."""
    col1 = get_or_create_author_collection(test_session, 'John Smith')
    assert col1 is not None
    assert col1.name == 'John Smith'
    assert col1.kind == 'author'

    # Same author returns same collection.
    col2 = get_or_create_author_collection(test_session, 'John Smith')
    assert col1.id == col2.id

    # Different author creates new collection.
    col3 = get_or_create_author_collection(test_session, 'Jane Doe')
    assert col3.id != col1.id

    # Empty author returns None.
    assert get_or_create_author_collection(test_session, '') is None
    assert get_or_create_author_collection(test_session, None) is None


def test_get_or_create_subject_collection(test_session):
    """Subject collections are created and reused."""
    col1 = get_or_create_subject_collection(test_session, 'Farming')
    assert col1 is not None
    assert col1.name == 'Farming'
    assert col1.kind == 'subject'

    col2 = get_or_create_subject_collection(test_session, 'Farming')
    assert col1.id == col2.id

    assert get_or_create_subject_collection(test_session, '') is None


def test_get_or_create_subject_collection_case_insensitive(test_session):
    """Subject collections with different casing reuse the same collection."""
    col1 = get_or_create_subject_collection(test_session, 'Science Fiction')
    col2 = get_or_create_subject_collection(test_session, 'science fiction')
    col3 = get_or_create_subject_collection(test_session, 'SCIENCE FICTION')
    assert col1.id == col2.id == col3.id


def test_get_or_create_author_collection_case_insensitive(test_session):
    """Author collections with different casing reuse the same collection."""
    col1 = get_or_create_author_collection(test_session, 'John Smith')
    col2 = get_or_create_author_collection(test_session, 'john smith')
    col3 = get_or_create_author_collection(test_session, 'JOHN SMITH')
    assert col1.id == col2.id == col3.id


@pytest.mark.asyncio
async def test_search_authors_by_name(test_session):
    """Search for author collections by partial name."""
    get_or_create_author_collection(test_session, 'John Smith')
    get_or_create_author_collection(test_session, 'Jane Doe')
    get_or_create_author_collection(test_session, 'Johnny Appleseed')

    # Partial match.
    results = await search_authors_by_name(test_session, 'john')
    assert len(results) == 2
    names = [r['name'] for r in results]
    assert 'John Smith' in names
    assert 'Johnny Appleseed' in names

    # No match.
    results = await search_authors_by_name(test_session, 'nobody')
    assert len(results) == 0

    # Limit.
    results = await search_authors_by_name(test_session, 'j', limit=1)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_subjects_by_name(test_session):
    """Search for subject collections by partial name."""
    get_or_create_subject_collection(test_session, 'Science Fiction')
    get_or_create_subject_collection(test_session, 'Computer Science')
    get_or_create_subject_collection(test_session, 'History')

    # Partial match.
    results = await search_subjects_by_name(test_session, 'science')
    assert len(results) == 2
    names = [r['name'] for r in results]
    assert 'Science Fiction' in names
    assert 'Computer Science' in names

    # No match.
    results = await search_subjects_by_name(test_session, 'nothing')
    assert len(results) == 0
