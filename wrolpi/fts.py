"""SQLite FTS5 full-text search for WROLPi.

This module owns everything FTS5: the DDL for the external-content tables and their sync
triggers, the websearch → FTS5 query translator, SQL fragment builders used by the search
call sites, and headline/snippet helpers.

No other module may contain FTS5 syntax (MATCH, bm25, snippet, highlight).

Design notes:
  * `file_group_fts` mirrors `file_group.a_text..d_text` (external content, so the text is
    stored once).  `content_rowid` requires `file_group.id` to be a true rowid alias
    ("INTEGER PRIMARY KEY" exactly) — see the model.
  * Ranking uses bm25 weights 10/4/2/1 which reproduce Postgres' A/B/C/D tsvector weighting.
    FTS5 `rank` is smaller-is-better (negative); this module always exposes `-rank AS ts_rank`
    so consumers keep the "higher is better" contract of `ts_rank`.
  * The "fast" search path (previously the `textsearch_abc` column) is a column filter that
    excludes `d_text`; the "deep" path searches all columns.
"""
import contextlib
import dataclasses
import re
import sqlite3
from typing import List, Optional, Tuple

FILE_GROUP_FTS_COLUMNS = ('a_text', 'b_text', 'c_text', 'd_text')
# The fast (non-deep) path searches these columns only.
ABC_COLUMNS = ('a_text', 'b_text', 'c_text')

# Reproduces ts_rank's default weights {D=0.1, C=0.2, B=0.4, A=1.0} (scaled x10), in FTS5
# column order (a_text..d_text).  Must have exactly one weight per FTS column.
FILE_GROUP_BM25_WEIGHTS = 'bm25(10.0, 4.0, 2.0, 1.0)'

TOKENIZER = 'porter unicode61'

# External-content FTS5 tables + the triggers that keep them in sync.
#
# The 'delete' command rows in the triggers must reproduce the OLD values exactly; never use
# INSERT OR REPLACE on file_group/doc_section (its implicit delete corrupts the FTS index),
# always ON CONFLICT ... DO UPDATE.
FTS_DDL = [
    f'''
    CREATE VIRTUAL TABLE IF NOT EXISTS file_group_fts USING fts5(
        a_text, b_text, c_text, d_text,
        content='file_group',
        content_rowid='id',
        tokenize='{TOKENIZER}'
    )
    ''',
    # Persist the weighted rank so bare `ORDER BY rank` uses the A/B/C/D weighting.
    f'''
    INSERT INTO file_group_fts(file_group_fts, rank) VALUES('rank', '{FILE_GROUP_BM25_WEIGHTS}')
    ''',
    '''
    CREATE TRIGGER IF NOT EXISTS file_group_fts_ai AFTER INSERT ON file_group BEGIN
        INSERT INTO file_group_fts(rowid, a_text, b_text, c_text, d_text)
        VALUES (new.id, new.a_text, new.b_text, new.c_text, new.d_text);
    END
    ''',
    '''
    CREATE TRIGGER IF NOT EXISTS file_group_fts_ad AFTER DELETE ON file_group BEGIN
        INSERT INTO file_group_fts(file_group_fts, rowid, a_text, b_text, c_text, d_text)
        VALUES ('delete', old.id, old.a_text, old.b_text, old.c_text, old.d_text);
    END
    ''',
    '''
    CREATE TRIGGER IF NOT EXISTS file_group_fts_au
    AFTER UPDATE OF a_text, b_text, c_text, d_text ON file_group BEGIN
        INSERT INTO file_group_fts(file_group_fts, rowid, a_text, b_text, c_text, d_text)
        VALUES ('delete', old.id, old.a_text, old.b_text, old.c_text, old.d_text);
        INSERT INTO file_group_fts(rowid, a_text, b_text, c_text, d_text)
        VALUES (new.id, new.a_text, new.b_text, new.c_text, new.d_text);
    END
    ''',
    f'''
    CREATE VIRTUAL TABLE IF NOT EXISTS doc_section_fts USING fts5(
        content,
        content='doc_section',
        content_rowid='id',
        tokenize='{TOKENIZER}'
    )
    ''',
    '''
    CREATE TRIGGER IF NOT EXISTS doc_section_fts_ai AFTER INSERT ON doc_section BEGIN
        INSERT INTO doc_section_fts(rowid, content) VALUES (new.id, new.content);
    END
    ''',
    '''
    CREATE TRIGGER IF NOT EXISTS doc_section_fts_ad AFTER DELETE ON doc_section BEGIN
        INSERT INTO doc_section_fts(doc_section_fts, rowid, content) VALUES ('delete', old.id, old.content);
    END
    ''',
    '''
    CREATE TRIGGER IF NOT EXISTS doc_section_fts_au AFTER UPDATE OF content ON doc_section BEGIN
        INSERT INTO doc_section_fts(doc_section_fts, rowid, content) VALUES ('delete', old.id, old.content);
        INSERT INTO doc_section_fts(rowid, content) VALUES (new.id, new.content);
    END
    ''',
]

# FTS5 shadow tables (and the virtual tables themselves); excluded from alembic autogenerate.
FTS_TABLE_PREFIXES = ('file_group_fts', 'doc_section_fts')


_ITEM_RE = re.compile(r'-?"[^"]*"?|\S+')
_WORD_RE = re.compile(r'\w+', re.UNICODE)


def _render_phrase(words: List[str]) -> str:
    """Render sanitized words as a (safe) FTS5 phrase: every term is double-quoted."""
    return '"' + ' '.join(words) + '"'


def translate_websearch(search_str: Optional[str], columns: Optional[Tuple[str, ...]] = None) -> Optional[str]:
    """Translate a websearch-style query (Postgres `websearch_to_tsquery` semantics) to FTS5.

    Supported semantics: bare words are ANDed, "double quotes" form phrases, `-term` excludes,
    a bare OR separates groups.  All user tokens end up inside double-quotes so no FTS5 syntax
    can be injected; the output either parses or is None (nothing usable to search).

    Punctuation is stripped from terms (`C++` -> `"C"`, `e.g.` -> the phrase `"e g"`).  This is
    NOT lossy relative to the index: the unicode61 tokenizer strips the same punctuation when
    indexing, so `C++` is stored as the token `c` — exactly as Postgres's `websearch_to_tsquery`
    ('C++' -> 'c') and `to_tsvector` did.  Punctuation is unsearchable under either engine's
    default tokenizer; matching it literally would require a custom FTS5 tokenizer.

    `columns` restricts matching to the given FTS columns (the fast/abc path).

    >>> translate_websearch('two words')
    '("two" AND "words")'
    >>> translate_websearch('"a phrase" -excluded')
    '(("a phrase") NOT "excluded")'
    >>> translate_websearch('cat OR dog')
    '("cat") OR ("dog")'
    """
    if not search_str or not search_str.strip():
        return None

    # Lex into items: quoted phrases (optionally negated) or bare tokens.
    items = []  # (negated: bool, words: List[str])
    for token in _ITEM_RE.findall(search_str):
        negated = token.startswith('-')
        if negated:
            token = token[1:]
        words = _WORD_RE.findall(token)
        if not words:
            continue  # pure punctuation
        items.append((negated, words))

    if not items:
        return None

    # Split on OR (websearch: a bare, un-negated, unquoted "or"; we accept any lone "or" token).
    groups: List[List[Tuple[bool, List[str]]]] = [[]]
    for negated, words in items:
        if not negated and len(words) == 1 and words[0].lower() == 'or':
            if groups[-1]:
                groups.append([])
            continue
        groups[-1].append((negated, words))

    rendered_groups = []
    for group in groups:
        positives = [_render_phrase(words) for negated, words in group if not negated]
        negatives = [_render_phrase(words) for negated, words in group if negated]
        if not positives:
            # FTS5 NOT is binary; a group with only negatives is not expressible.  Postgres
            # would match "everything not containing the term" -- accepted divergence: skip.
            continue
        expr = '(' + ' AND '.join(positives) + ')'
        for negative in negatives:
            expr = f'({expr} NOT {negative})'
        rendered_groups.append(expr)

    if not rendered_groups:
        return None

    result = ' OR '.join(f'({group})' for group in rendered_groups)
    if columns:
        result = '{' + ' '.join(columns) + '} : (' + result + ')'
    return result


@dataclasses.dataclass
class FileGroupSearch:
    """SQL fragments for joining file_group against its FTS5 table.

    Use in a query like:
        SELECT fg.id, {rank_select} FROM file_group fg {join} WHERE {where} ORDER BY 2 DESC
    """
    join: str  # JOIN clause linking file_group_fts to file_group (aliased fg)
    where: str  # MATCH condition
    rank_select: str  # positive higher-is-better rank, SELECTable as ts_rank
    params: dict  # bind parameters used by the fragments


def file_group_search(search_str: str, deep: bool = False,
                      fg_alias: str = 'fg', param_name: str = 'fts_match') -> Optional[FileGroupSearch]:
    """Build the FTS5 join/where/rank fragments for a file_group search.

    Returns None when there is nothing usable to search; callers must then treat the request
    like an empty search (no rank column, no MATCH condition)."""
    columns = None if deep else ABC_COLUMNS
    match = translate_websearch(search_str, columns=columns)
    if match is None:
        return None
    return FileGroupSearch(
        join=f'JOIN file_group_fts fts ON fts.rowid = {fg_alias}.id',
        where=f'fts.file_group_fts MATCH :{param_name}',
        rank_select='-fts.rank AS ts_rank',
        params={param_name: match},
    )


def file_group_search_join(search_str: str, deep: bool = False, headlines: bool = False,
                           fg_alias: str = 'fg', param_name: str = 'fts_match',
                           start: str = '<b>', stop: str = '</b>', tokens: int = 16) -> Optional[FileGroupSearch]:
    """Subquery-join form of `file_group_search`.

    SQLite refuses FTS5 auxiliary functions (snippet) in a query that also uses window functions
    (e.g. COUNT(*) OVER()), so the rank and snippets are computed inside a subquery and joined.
    The returned `join` both filters (INNER JOIN on the MATCH) and provides `fts.ts_rank` (and
    `fts.b_headline`/`c_headline`/`d_headline` when `headlines`); `where` is empty."""
    columns = None if deep else ABC_COLUMNS
    match = translate_websearch(search_str, columns=columns)
    if match is None:
        return None
    snippet_selects = ''
    if headlines:
        snippet_selects = (f", snippet(file_group_fts, 1, '{start}', '{stop}', '…', {tokens}) AS b_headline"
                           f", snippet(file_group_fts, 2, '{start}', '{stop}', '…', {tokens}) AS c_headline"
                           f", snippet(file_group_fts, 3, '{start}', '{stop}', '…', {tokens}) AS d_headline")
    join = (f'JOIN (SELECT rowid, -rank AS ts_rank{snippet_selects} FROM file_group_fts '
            f'WHERE file_group_fts MATCH :{param_name}) fts ON fts.rowid = {fg_alias}.id')
    return FileGroupSearch(join=join, where='', rank_select='fts.ts_rank AS ts_rank',
                           params={param_name: match})


def file_group_headline_selects(start: str = '<b>', stop: str = '</b>', tokens: int = 16) -> str:
    """SELECT fragments producing the b/c/d headline columns from the joined FTS table.

    `title_headline` is not produced here: `title` is not an FTS column; use `headline_texts`
    on the result rows (matches the old ts_headline-over-title behavior)."""
    return f''',
           snippet(file_group_fts, 1, '{start}', '{stop}', '…', {tokens}) AS b_headline,
           snippet(file_group_fts, 2, '{start}', '{stop}', '…', {tokens}) AS c_headline,
           snippet(file_group_fts, 3, '{start}', '{stop}', '…', {tokens}) AS d_headline'''


def headline_texts(entries: List[Optional[str]], search_str: str,
                   start: str = '<b>', stop: str = '</b>', tokens: int = 8) -> List[Tuple[str, float]]:
    """Highlight `search_str` matches in ad-hoc strings; returns [(headline, rank), ...].

    Replaces Postgres `ts_headline`/`ts_rank` over arbitrary content (Zim search results,
    FileGroup titles).  Uses a throwaway in-memory FTS5 table so stemming matches the real
    search index.  Non-matching entries yield the start of the text with rank 0."""

    def _lead(text: Optional[str]) -> str:
        words = (text or '').split()
        return ' '.join(words[:tokens])

    results = [(_lead(text), 0.0) for text in entries]

    match = translate_websearch(search_str)
    if match is None or not entries:
        return results

    with contextlib.closing(sqlite3.connect(':memory:')) as conn:
        conn.execute(f"CREATE VIRTUAL TABLE h USING fts5(content, tokenize='{TOKENIZER}')")
        conn.executemany('INSERT INTO h(rowid, content) VALUES (?, ?)',
                         [(idx, text or '') for idx, text in enumerate(entries)])
        curs = conn.execute(
            f"SELECT rowid, snippet(h, 0, ?, ?, '…', ?), rank FROM h WHERE h MATCH ?",
            (start, stop, tokens, match))
        for rowid, headline, rank in curs.fetchall():
            results[rowid] = (headline, -rank)

    return results


def rebuild_fts(curs):
    """Rebuild the FTS5 indexes from their content tables (e.g. after a bulk import)."""
    curs.execute("INSERT INTO file_group_fts(file_group_fts) VALUES('rebuild')")
    curs.execute("INSERT INTO doc_section_fts(doc_section_fts) VALUES('rebuild')")


def optimize_fts(curs):
    """Merge FTS5 b-trees for faster queries; call after large refreshes."""
    curs.execute("INSERT INTO file_group_fts(file_group_fts) VALUES('optimize')")
    curs.execute("INSERT INTO doc_section_fts(doc_section_fts) VALUES('optimize')")


def fts_integrity_ok(curs) -> bool:
    """Verify the FTS5 indexes match their content tables."""
    try:
        curs.execute("INSERT INTO file_group_fts(file_group_fts, rank) VALUES('integrity-check', 1)")
        curs.execute("INSERT INTO doc_section_fts(doc_section_fts, rank) VALUES('integrity-check', 1)")
        return True
    except sqlite3.DatabaseError:
        return False
    except Exception as e:
        # SQLAlchemy-wrapped DatabaseError.
        if 'malformed' in str(e) or 'corrupt' in str(e).lower():
            return False
        raise
