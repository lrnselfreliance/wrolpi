"""Tests for wrolpi.fts: the websearch → FTS5 translator, DDL/sync triggers, and headlines."""
import sqlite3

import pytest

from wrolpi import fts


@pytest.mark.parametrize('search_str,expected', [
    ('one', '(("one"))'),
    ('two words', '(("two" AND "words"))'),
    ('"a phrase"', '(("a phrase"))'),
    ('"a phrase" extra', '(("a phrase" AND "extra"))'),
    ('word -excluded', '((("word") NOT "excluded"))'),
    ('-only', None),  # all-negative is not expressible in FTS5; treated as nothing to search
    ('cat OR dog', '(("cat")) OR (("dog"))'),
    ('or', None),  # a lone OR is not a search
    ('cat OR OR dog', '(("cat")) OR (("dog"))'),
    ('OR cat', '(("cat"))'),
    ("don't", '(("don t"))'),  # punctuation-joined tokens become a phrase, like websearch
    ('!!! ...', None),  # pure punctuation
    ('', None),
    (None, None),
    ('   ', None),
])
def test_translate_websearch(search_str, expected):
    assert fts.translate_websearch(search_str) == expected


def test_translate_websearch_columns():
    result = fts.translate_websearch('word', columns=fts.ABC_COLUMNS)
    assert result == '{a_text b_text c_text} : ((("word")))'


@pytest.mark.parametrize('garbage', [
    '"', '((', 'NOT', '-', '*', 'a:b^c', '"unclosed', 'a AND OR NOT -', '{}', 'a"b"c',
    '-"neg phrase" -word', 'OR OR OR', '(((((', '%%%', 'term*', 'a NEAR b', '":"',
])
def test_translate_websearch_fuzz(garbage):
    """Translator output must either be None or parse without an FTS5 syntax error."""
    result = fts.translate_websearch(garbage)
    if result is None:
        return
    with sqlite3.connect(':memory:') as conn:
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(a_text, b_text, c_text, d_text)")
        # Raises sqlite3.OperationalError on FTS5 syntax errors.
        conn.execute('SELECT * FROM t WHERE t MATCH ? LIMIT 1', (result,)).fetchall()


@pytest.fixture
def fts_db():
    """A scratch DB with a minimal file_group/doc_section and the real FTS DDL + triggers."""
    conn = sqlite3.connect(':memory:')
    conn.executescript('''
        CREATE TABLE file_group (id INTEGER PRIMARY KEY, a_text TEXT, b_text TEXT, c_text TEXT, d_text TEXT);
        CREATE TABLE doc_section (id INTEGER PRIMARY KEY, content TEXT);
    ''')
    for statement in fts.FTS_DDL:
        conn.execute(statement)
    yield conn
    conn.close()


def test_fts_sync_triggers(fts_db):
    """INSERT/UPDATE/DELETE on file_group keep the FTS index in sync."""
    fts_db.execute("INSERT INTO file_group (id, a_text, d_text) VALUES (1, 'Cooking Rice', 'boil the water')")
    fts_db.execute("INSERT INTO file_group (id, a_text) VALUES (2, 'Gardening')")

    def match(query, deep=True):
        columns = None if deep else fts.ABC_COLUMNS
        expr = fts.translate_websearch(query, columns=columns)
        return [row[0] for row in
                fts_db.execute('SELECT rowid FROM file_group_fts WHERE file_group_fts MATCH ?', (expr,))]

    assert match('cooking') == [1]
    # Stemming: porter maps "gardens" and "gardening" to the same stem.
    assert match('gardens') == [2]
    # Fast path does not search d_text.
    assert match('boil', deep=True) == [1]
    assert match('boil', deep=False) == []

    # UPDATE of an indexed column.
    fts_db.execute("UPDATE file_group SET a_text = 'Baking Bread' WHERE id = 1")
    assert match('cooking') == []
    assert match('baking') == [1]

    # DELETE removes from the index.
    fts_db.execute('DELETE FROM file_group WHERE id = 1')
    assert match('baking') == []

    # Integrity check passes after all of the above.
    assert fts.fts_integrity_ok(fts_db) is True


def test_fts_rank_weights(fts_db):
    """A match in a_text (weight 10) outranks the same match in d_text (weight 1)."""
    fts_db.execute("INSERT INTO file_group (id, a_text) VALUES (1, 'solar power')")
    fts_db.execute("INSERT INTO file_group (id, d_text) VALUES (2, 'solar power')")
    expr = fts.translate_websearch('solar')
    rows = fts_db.execute(
        'SELECT rowid, -rank FROM file_group_fts WHERE file_group_fts MATCH ? ORDER BY rank',
        (expr,)).fetchall()
    assert [row[0] for row in rows] == [1, 2]
    assert rows[0][1] > rows[1][1] > 0  # exposed rank is positive, higher is better


def test_doc_section_fts(fts_db):
    fts_db.execute("INSERT INTO doc_section (id, content) VALUES (7, 'the fire needs oxygen')")
    expr = fts.translate_websearch('oxygen')
    rows = fts_db.execute(
        "SELECT rowid, snippet(doc_section_fts, 0, '[', ']', '…', 5) FROM doc_section_fts "
        "WHERE doc_section_fts MATCH ?", (expr,)).fetchall()
    assert rows[0][0] == 7
    assert '[oxygen]' in rows[0][1]


def test_headline_texts():
    entries = ['the quick brown fox jumps', 'nothing to see here', None]
    results = fts.headline_texts(entries, 'foxes jumping')  # stems match fox/jumps
    assert '<b>fox</b>' in results[0][0] and '<b>jumps</b>' in results[0][0]
    assert results[0][1] > 0
    # Non-matching entries return the start of the text with rank 0.
    assert results[1] == ('nothing to see here', 0.0)
    assert results[2] == ('', 0.0)


def test_headline_texts_no_search():
    results = fts.headline_texts(['some text'], '')
    assert results == [('some text', 0.0)]


STEMMING_DOCS = {
    1: 'watch the sunrise',
    2: 'he watches birds',
    3: 'she watched a movie',
    4: 'watching the stars',
    5: 'jump the fence',
    6: 'she jumps high',
    7: 'jumping and jumped all day',
    8: 'run to the store',
    9: 'she runs fast',
    10: 'I go running daily',
    11: 'fish in the lake',
    12: 'he fishes and fished',
    13: 'fishing is relaxing',
    14: 'a cat sleeps',
    15: 'two cats play',
    16: 'the dog barks',
    17: 'three dogs howl',
}

WATCH, JUMP, RUN, FISH = [1, 2, 3, 4], [5, 6, 7], [8, 9, 10], [11, 12, 13]


@pytest.mark.parametrize('query,expected', [
    # Every inflectional variant matches every other variant of its word.
    ('watch', WATCH), ('watches', WATCH), ('watched', WATCH), ('watching', WATCH),
    ('jump', JUMP), ('jumps', JUMP), ('jumping', JUMP), ('jumped', JUMP),
    ('run', RUN), ('runs', RUN), ('running', RUN),
    ('fish', FISH), ('fishes', FISH), ('fished', FISH), ('fishing', FISH),
    ('cat', [14, 15]), ('cats', [14, 15]),
    ('dog', [16, 17]), ('dogs', [16, 17]),
    # Documented boundary (identical to the old Postgres snowball behavior): stemmers strip
    # grammatical suffixes, they do not lemmatize -- derived words like "runner" are their own
    # terms and do not match the "run" family.
    ('runner', []),
])
def test_stemming(fts_db, query, expected):
    """Searching any grammatical variant of a word matches all other variants.

    This contract is load-bearing: users search "running" and expect files titled
    "runs"/"run" to match.  The Porter stemmer provides it at index AND query time."""
    for rowid, text in STEMMING_DOCS.items():
        fts_db.execute('INSERT INTO file_group (id, a_text) VALUES (?, ?)', (rowid, text))

    match = fts.translate_websearch(query)
    rows = [row[0] for row in
            fts_db.execute('SELECT rowid FROM file_group_fts WHERE file_group_fts MATCH ? ORDER BY rowid', (match,))]
    assert rows == expected


def test_stemming_headlines_agree_with_matching(fts_db):
    """The headline helper uses the same tokenizer, so highlights agree with matches."""
    results = fts.headline_texts(['he watches birds', 'a marathon runner'], 'watching')
    assert results[0] == ('he <b>watches</b> birds', results[0][1])
    assert results[0][1] > 0
    # "runner" did not match "watching"; the entry returns leading text with rank 0.
    assert results[1] == ('a marathon runner', 0.0)
