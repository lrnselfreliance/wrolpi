"""Tests for the shared FileGroup modeler loop."""
from unittest.mock import patch

import pytest

from wrolpi.files.modeler import run_modeler_loop, SkipModeler
from wrolpi.files.models import FileGroup


def _select_unindexed(session, skip_ids):
    query = session.query(FileGroup.id).filter(FileGroup.indexed != True)
    if skip_ids:
        query = query.filter(FileGroup.id.notin_(skip_ids))
    return [row[0] for row in query.limit(2).all()]


@pytest.mark.asyncio
async def test_run_modeler_loop_pages_and_skips_failures(test_session, test_directory, make_files_structure):
    """The loop pages by batch_size and does not re-select a FileGroup that failed this run."""
    paths = make_files_structure([f'd{i}.txt' for i in range(5)])
    fgs = [FileGroup.from_paths(test_session, p) for p in paths]
    test_session.commit()
    ids = [fg.id for fg in fgs]
    boom_id = ids[1]
    applied = []

    def select_ids(session, skip_ids):
        return _select_unindexed(session, skip_ids)

    def apply(session, file_group, prepared):
        if file_group.id == boom_id:
            raise RuntimeError('boom')
        applied.append(file_group.id)
        file_group.model = 'file'

    # PYTEST re-raises apply failures; disable that so we exercise skip-and-continue.
    with patch('wrolpi.files.modeler.PYTEST', False):
        await run_modeler_loop(
            name='test_modeler',
            batch_size=2,
            select_ids=select_ids,
            apply=apply,
            txn='batch',
        )

    assert boom_id not in applied
    assert set(applied) == set(ids) - {boom_id}
    test_session.expire_all()
    by_id = {fg.id: fg for fg in test_session.query(FileGroup)}
    assert by_id[boom_id].indexed is not True
    for i in applied:
        assert by_id[i].indexed is True


@pytest.mark.asyncio
async def test_run_modeler_loop_skip_modeler_leaves_unindexed(test_session, test_directory, make_files_structure):
    """SkipModeler leaves indexed=False so a leftover indexer can claim the FileGroup."""
    path, = make_files_structure(['page.html'])
    fg = FileGroup.from_paths(test_session, path)
    test_session.commit()

    def select_ids(session, skip_ids):
        if skip_ids:
            return []
        return [fg.id]

    def apply(session, file_group, prepared):
        raise SkipModeler

    await run_modeler_loop(
        name='test_skip',
        batch_size=10,
        select_ids=select_ids,
        apply=apply,
        txn='batch',
    )

    test_session.expire_all()
    assert test_session.query(FileGroup).one().indexed is not True


@pytest.mark.asyncio
async def test_run_modeler_loop_per_item_lock_retry(test_session, test_directory, make_files_structure):
    """per_item txn models each FileGroup in its own write transaction."""
    paths = make_files_structure(['a.pdf', 'b.pdf'])
    fgs = [FileGroup.from_paths(test_session, p) for p in paths]
    test_session.commit()
    ids = [fg.id for fg in fgs]
    applied = []

    def select_ids(session, skip_ids):
        return [i for i in ids if i not in skip_ids]

    def apply(session, file_group, prepared):
        applied.append(file_group.id)

    await run_modeler_loop(
        name='test_per_item',
        batch_size=10,
        select_ids=select_ids,
        apply=apply,
        txn='per_item',
        lock_retries=3,
    )

    assert applied == ids
    test_session.expire_all()
    assert all(fg.indexed is True for fg in test_session.query(FileGroup))
