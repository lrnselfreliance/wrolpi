"""Which saved version of each database config the database is in step with.

A database config (tags.yaml, channels.yaml, ...) saves rows the database owns.  Its file carries an integer
`version`; the database keeps one too, in `config_version`.  Every change to rows a config owns adds one to that
config's database version, in the same transaction (`_count_config_changes`).  `dump_config` writes the database's
version into the file it saves, and an import records the file's version once it has applied it.

So an import can tell which side is newer by comparing two integers (see `ConfigFile.import_decision`):

* file == database: in step.  The file is current; import it, deleting what it no longer lists.
* file > database: the file is newer (a restored or wiped database, a copied config); import it the same way.
* file < database: the database changed and was not saved yet (e.g. WROLPi restarted first).  Save the database
  instead of importing the older file, which would undo those changes.
* no database row: not known yet (a config never imported by this code).  Import without deleting.

Integers only: a Raspberry Pi has no clock that survives a reboot, so timestamps cannot order these.
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, List, Optional, Set, Type

import sqlite3

from sqlalchemy import Column, Integer, String, event, inspect, text
from sqlalchemy.orm import Session

from wrolpi.common import Base


class ConfigVersion(Base):
    __tablename__ = 'config_version'
    name = Column(String, primary_key=True)  # The config's file_name, e.g. "tags.yaml".
    version = Column(Integer, nullable=False)

    def __repr__(self):
        return f'<ConfigVersion {self.name}={self.version}>'


@dataclass(frozen=True)
class Ownership:
    config: str
    model: Type
    # Only changes to these columns count; None counts every column.
    columns: Optional[FrozenSet[str]] = None
    # Only rows this accepts belong to the config (e.g. Collections of one kind); None accepts every row.
    row: Optional[Callable] = None


OWNERSHIPS: Dict[Type, List[Ownership]] = defaultdict(list)


def register_ownership(config: str, model: Type, columns: Set[str] = None, row: Callable = None):
    """Declare that `config` (a file_name) saves `model`'s rows, so changing them makes the database newer than
    the config file until it is saved again."""
    OWNERSHIPS[model].append(Ownership(config, model, frozenset(columns) if columns else None, row))


def versioned_config_names() -> Set[str]:
    return {o.config for ownerships in OWNERSHIPS.values() for o in ownerships}


def _owners(obj, changed: bool) -> Set[str]:
    """The configs that save `obj`.  `changed`: only those whose columns of an updated row changed; otherwise (an
    inserted or deleted row) only those whose columns have a value."""
    names = set()
    for ownership in OWNERSHIPS.get(type(obj), ()):
        # Columns first: `row` may query (e.g. `collection_kind`).
        if changed:
            state = inspect(obj)
            columns = ownership.columns or [i.key for i in state.mapper.column_attrs]
            if not any(state.attrs[i].history.has_changes() for i in columns):
                continue
        elif ownership.columns and all(getattr(obj, i) is None for i in ownership.columns):
            # e.g. a FileGroup that was never viewed is not in recently_viewed.yaml.
            continue
        if ownership.row and not ownership.row(obj):
            continue
        names.add(ownership.config)
    return names


@event.listens_for(Session, 'after_flush')
def _count_config_changes(session: Session, flush_context):
    """Add one to the database version of each config whose rows this flush changed, in the same transaction.

    Only existing rows are counted: a config without a row is not known yet, and its next import creates the row.
    Raw SQL writes to owned tables are not seen here; they must call `count_config_change`."""
    if not OWNERSHIPS:
        return
    names = set()
    for obj in session.new:
        names |= _owners(obj, changed=False)
    for obj in session.deleted:
        names |= _owners(obj, changed=False)
    for obj in session.dirty:
        names |= _owners(obj, changed=True)
    if names:
        count_config_change(session, *names)


def count_config_change(session: Session, *names: str):
    """Add one to these configs' database versions (only those which have one)."""
    params = {f'n{i}': name for i, name in enumerate(names)}
    placeholders = ', '.join(f':{i}' for i in params)
    session.connection().execute(
        text(f'UPDATE config_version SET version = version + 1 WHERE name IN ({placeholders})'), params)


def count_config_change_curs(curs, *names: str):
    """`count_config_change` for a raw `sqlite3` cursor, in its transaction."""
    placeholders = ', '.join('?' for _ in names)
    try:
        curs.execute(f'UPDATE config_version SET version = version + 1 WHERE name IN ({placeholders})', names)
    except sqlite3.OperationalError as e:
        # A migration older than config_version runs this code too.
        if 'no such table' not in str(e):
            raise


def collection_kind(obj) -> Optional[str]:
    """The kind of the Collection `obj` (e.g. a Download) belongs to, read on its flush's connection."""
    if not getattr(obj, 'collection_id', None):
        return None
    session = Session.object_session(obj)
    row = session.connection().execute(
        text('SELECT kind FROM collection WHERE id = :id'), {'id': obj.collection_id}).first()
    return row[0] if row else None


def get_config_version(session: Session, name: str) -> Optional[int]:
    row = session.connection().execute(
        text('SELECT version FROM config_version WHERE name = :name'), {'name': name}).first()
    return row[0] if row else None


def set_config_version(session: Session, name: str, version: int):
    session.connection().execute(
        text('INSERT INTO config_version (name, version) VALUES (:name, :version) '
             'ON CONFLICT (name) DO UPDATE SET version = excluded.version'),
        {'name': name, 'version': version})


IMPORT = 'import'
IMPORT_WITHOUT_DELETES = 'import_without_deletes'
SAVE = 'save'


def decide(file_version: int, db_version: Optional[int]) -> str:
    """The table in this module's docstring."""
    if db_version is None:
        return IMPORT_WITHOUT_DELETES
    if file_version < db_version:
        return SAVE
    return IMPORT
