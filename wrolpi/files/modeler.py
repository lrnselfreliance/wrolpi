"""Shared FileGroup modeler batch loop.

Each module still owns select / prepare / apply.  This loop owns:

- paging by batch_size
- a per-run skip set so failures cannot re-select forever
- cancel yields
- progress_callback
- two transaction styles: one write per batch (video, zim, archive) or one write
  per item with lock retries (docs)

Video still probes outside the write lock via ``prepare``.  Archive uses
``SkipModeler`` for HTML that is not a SingleFile so apply_indexers can claim it.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Iterable

from sqlalchemy.exc import OperationalError

from wrolpi.common import logger
from wrolpi.db import get_db_session
from wrolpi.files.models import FileGroup
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

SelectIds = Callable  # (session, skip_ids: set) -> list[int]
Prepare = Callable  # async (ids: list[int]) -> dict
Apply = Callable  # (session, file_group, prepared) -> None


class SkipModeler(Exception):
    """This FileGroup is not this modeler's type.  Leave indexed=False so leftovers can claim it."""


async def run_modeler_loop(
        *,
        name: str,
        batch_size: int,
        select_ids: SelectIds,
        apply: Apply,
        prepare: Prepare | None = None,
        txn: str = 'batch',
        lock_retries: int = 1,
        mark_indexed_on_failure: bool = False,
        progress_callback: Callable[[int], None] | None = None,
):
    """Page FileGroups and apply a modeler until a short batch or empty select.

    ``txn='batch'``: one write transaction per page (video, zim, archive).
    ``txn='per_item'``: one write transaction per FileGroup (docs).
    """
    if txn not in ('batch', 'per_item'):
        raise ValueError(f'Unknown modeler txn {txn!r}')

    skip_ids: set = set()
    total_processed = 0
    while True:
        with get_db_session() as session:
            ids = list(select_ids(session, skip_ids))
        if not ids:
            break

        prepared = {}
        if prepare is not None:
            prepared = await prepare(ids) or {}

        if txn == 'batch':
            await _apply_batch(
                name, ids, prepared, apply, skip_ids, mark_indexed_on_failure,
            )
        else:
            await _apply_per_item(
                name, ids, prepared, apply, skip_ids, lock_retries,
            )

        total_processed += len(ids)
        if progress_callback:
            progress_callback(total_processed)

        logger.debug(f'{name}: modeled {len(ids)} FileGroups')

        if len(ids) < batch_size:
            break
        await asyncio.sleep(0)


async def _apply_batch(
        name: str,
        ids: list[int],
        prepared: dict,
        apply: Apply,
        skip_ids: set,
        mark_indexed_on_failure: bool,
):
    try:
        with get_db_session(commit=True) as session:
            file_groups: Iterable[FileGroup] = session.query(FileGroup).filter(FileGroup.id.in_(ids))
            for file_group in file_groups:
                try:
                    apply(session, file_group, prepared)
                    file_group.indexed = True
                except SkipModeler:
                    file_group.indexed = False
                    skip_ids.add(file_group.id)
                except Exception as e:
                    skip_ids.add(file_group.id)
                    if mark_indexed_on_failure:
                        file_group.indexed = True
                    logger.error(f'{name}: unable to model file_group_id={file_group.id}', exc_info=e)
                    if PYTEST:
                        raise
    except Exception as e:
        # One poisoned commit must not kill the modeler.  Skip this page for the rest of
        # the run; the next refresh retries it.
        skip_ids.update(ids)
        logger.error(f'{name}: failed to commit batch of {len(ids)} FileGroups', exc_info=e)
        if PYTEST:
            raise


async def _apply_per_item(
        name: str,
        ids: list[int],
        prepared: dict,
        apply: Apply,
        skip_ids: set,
        lock_retries: int,
):
    for fg_id in ids:
        for attempt in range(lock_retries):
            try:
                with get_db_session(commit=True) as session:
                    file_group = session.query(FileGroup).get(fg_id)
                    if file_group is None:
                        break
                    apply(session, file_group, prepared)
                    file_group.indexed = True
                break
            except SkipModeler:
                skip_ids.add(fg_id)
                break
            except OperationalError as e:
                if 'locked' in str(e).lower() and attempt < lock_retries - 1:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                logger.error(f'{name}: failed to model file_group_id={fg_id}: database error', exc_info=e)
                skip_ids.add(fg_id)
                break
            except Exception as e:
                # Do not touch the ORM object: after a failed flush the session is rolled back.
                logger.error(f'{name}: failed to model file_group_id={fg_id}', exc_info=e)
                skip_ids.add(fg_id)
                if PYTEST:
                    raise
                break
        await asyncio.sleep(0)


def skip_clause(query, column, skip_ids: set):
    """Exclude ids already failed/rejected this run."""
    if skip_ids:
        query = query.filter(column.notin_(skip_ids))
    return query
