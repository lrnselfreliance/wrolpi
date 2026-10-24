"""Importing a database config: read its file, diff it against a snapshot of the database, then write only the
differences in one short write (see `ConfigFile.import_config`).

A config declares a `ConfigSection` for each kind of row it saves (tags.yaml has Tags and the files they tag).
Rows are compared as plain data keyed the way the file names them (a URL, a name, a path), so the snapshot needs no
ORM objects and the read can finish before any slow preparation starts.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Hashable, Iterable, List, Set, Tuple

from sqlalchemy.orm import Session


@dataclass
class SectionDiff:
    """What applying a config file changes in one section.  Rows are the file's, as `ConfigSection.file_rows`
    returns them."""
    added: Dict[Hashable, dict] = field(default_factory=dict)
    changed: Dict[Hashable, dict] = field(default_factory=dict)
    removed: Set[Hashable] = field(default_factory=set)

    def __bool__(self):
        return bool(self.added or self.changed or self.removed)


class ConfigSection:
    """One kind of row a database config saves.

    Subclasses define how a file row and a database row become the same comparable dict (the values the config
    saves, keyed by `key`), and how to write the differences."""
    name: str = None

    def file_rows(self, config: dict) -> Tuple[Dict[Hashable, dict], Set[Hashable]]:
        """The rows this section of `config` (the file's data) lists, keyed, plus the keys of rows that are invalid.
        An invalid row is skipped, but its key counts as listed, so it is never deleted."""
        raise NotImplementedError()

    def db_rows(self, session: Session) -> Dict[Hashable, dict]:
        """The rows the config saves, keyed and compared like `file_rows`.  Rows the config never saves are left
        out: they are never "removed"."""
        raise NotImplementedError()

    def upsert(self, session: Session, rows: Dict[Hashable, dict]):
        """Write these added or changed rows.  Fetch the current rows by key first: one may have been created or
        deleted since the snapshot."""
        raise NotImplementedError()

    def delete(self, session: Session, keys: Set[Hashable]):
        """Delete the rows with these keys.  A row deleted since the snapshot, or no longer saved by the config, is
        left alone."""
        raise NotImplementedError()


def diff_section(file_rows: Dict[Hashable, dict], invalid_keys: Set[Hashable], db_rows: Dict[Hashable, dict],
                 deletes: bool) -> SectionDiff:
    """Compare a section's file rows with its database rows.  `deletes`: rows the file no longer lists are removed.
    An empty section never removes anything: it cannot be told apart from a lost or blanked file."""
    diff = SectionDiff()
    for key, row in file_rows.items():
        if key not in db_rows:
            diff.added[key] = row
        elif db_rows[key] != row:
            diff.changed[key] = row
    if deletes and (file_rows or invalid_keys):
        diff.removed = db_rows.keys() - file_rows.keys() - invalid_keys
    return diff


def chunks(items: Iterable[Any], size: int = 500) -> Iterable[List[Any]]:
    """Split `items` for `IN (...)` queries (SQLite limits the parameters of one statement)."""
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]
