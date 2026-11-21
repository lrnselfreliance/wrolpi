"""
Sync API endpoints for WROLPi Controller: a secondary WROLPi copying its primary (see controller.lib.sync).

The Controller answers these because the API is stopped while a sync runs.
"""

import asyncio

from fastapi import APIRouter, HTTPException

from controller.lib import sync

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status")
async def sync_status() -> dict:
    """The progress and outcome of this secondary's sync."""
    return sync.get_status()


@router.post("/run", status_code=202)
async def sync_run() -> dict:
    """Copy the primary now."""
    if reason := await asyncio.to_thread(sync.skip_reason):
        raise HTTPException(status_code=409, detail=reason)
    # Kept referenced, or the task could be collected while the sync runs.
    router.sync_task = asyncio.create_task(asyncio.to_thread(sync.run_sync))
    return {"success": True}


@router.post("/cancel", status_code=202)
async def sync_cancel() -> dict:
    """Stop the running sync; the API is started again."""
    sync.request_cancel()
    return {"success": True}
